// SPDX-License-Identifier: CC-BY-NC-SA-4.0
// 本项目有权许可的新增贡献适用；上游鸣潮/大卡猫形象的 CC 授权未确认。
// 第三方组件保留原许可，范围及公益声明见《项目开发文档》。
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Media.Animation;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using LinePutScript;
using VPet_Simulator.Core;
using static VPet_Simulator.Core.GraphInfo; // GraphType/AnimatType 是 GraphInfo 的嵌套枚举
using MainDisplay = VPet_Simulator.Core.Main;

namespace DakamaoPet
{
    /// <summary>
    /// 极简桌宠宿主：透明窗口 + VPet 动画引擎。
    /// 只负责"序列帧动画播放 / 拖拽 / 摸头摸身 / 松手重力下落"，不含养成、投喂、工作等游戏系统。
    /// </summary>
    public partial class PetWindow : Window, IController
    {
        public GameCore Core;
        private MainDisplay? _main;
        private bool _petReady;

        // Fall motion is tied to the desktop floor; impact art starts on collision.
        private bool _falling;
        private bool _landing;
        private bool _handleDragging;
        private Point _dragCursorStart;
        private Point _dragWindowStart;
        private Point _lastDragCursor;
        private double _swayAngle;
        private double _swayTarget;
        private double _swayVelocity;
        private double _swayLargestLeft;
        private double _swayLargestRight;
        private long _lastDragMoveTicks;
        private readonly Stopwatch _swayClock = new Stopwatch();
        private DispatcherTimer? _swayTimer;
        private double _fallSpeed;
        private int _fallSequence;
        private readonly Stopwatch _fallClock = new Stopwatch();
        private DispatcherTimer? _fallTimer;
        private readonly Dictionary<string, List<PNGAnimation>> _previewActions = new();
        private bool _actionRingReady;
        private DispatcherTimer? _previewTimer;
        private System.Collections.Generic.List<PNGAnimation>? _previewSequence;
        private int _previewIndex;
        private int _previewGeneration;
        private Action? _pendingAction;
        private string? _sleepAction;
        private bool _sleepReady;
        private bool _sleepResponding;
        private bool _nextSleepBellyUp;
        private int _sleepGeneration;
        private bool _sleepWakeRequested;
        private bool _sleepWaking;
        private bool _sleepSwitchRequested;
        private Action? _afterSleepWake;
        private Point _lastHeadTouchPoint;
        private Rect _frontTouchBounds;
        private double _frontTouchSplit;
        private static readonly JsonDocument AnimationTiming = LoadAnimationTiming();

        [StructLayout(LayoutKind.Sequential)]
        private struct NativeRect
        {
            public int Left;
            public int Top;
            public int Right;
            public int Bottom;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct NativePoint
        {
            public int X;
            public int Y;
        }

        [StructLayout(LayoutKind.Sequential)]
        private struct MonitorInfo
        {
            public int Size;
            public NativeRect Monitor;
            public NativeRect Work;
            public uint Flags;
        }

        [DllImport("user32.dll")]
        private static extern IntPtr MonitorFromWindow(IntPtr window, uint flags);

        [DllImport("user32.dll")]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool GetMonitorInfo(IntPtr monitor, ref MonitorInfo info);

        [DllImport("user32.dll")]
        [return: MarshalAs(UnmanagedType.Bool)]
        private static extern bool GetCursorPos(out NativePoint point);

        public PetWindow()
        {
            InitializeComponent();
            LoadPetSize();
            InitializeDesktopSettings();
            InitializePositionTracking();
            Core = new GameCore
            {
                Controller = this,
                Save = new GameSave("大卡猫")
            };
            Loaded += PetWindow_Loaded;
            ContentRendered += (_, _) =>
            {
                RestorePosition();
                InitializeTray();
                App.WriteLog("READY window=" + ActualWidth + "x" + ActualHeight
                    + " left=" + Left.ToString("F0") + " top=" + Top.ToString("F0"));
            };
            Closed += (_, _) =>
            {
                FlushPositionSave();
                FlushSizeSettings();
                CloseTray();
                CancelWalk();
                CancelFall();
                _swayTimer?.Stop();
                _previewTimer?.Stop();
                StopFluidPlayback();
                CloseDesktopSettings();
            };

            AddHandler(PreviewMouseLeftButtonDownEvent, new MouseButtonEventHandler((_, e) =>
            {
                // Popup controls have their own presentation source. Let the
                // slider receive its press/capture instead of petting or grabbing.
                if (e.OriginalSource is DependencyObject source &&
                    PresentationSource.FromDependencyObject(source) != PresentationSource.FromVisual(this))
                    return;
                if (!_petReady)
                {
                    e.Handled = true;
                    return;
                }
                var point = e.GetPosition(DragHandle);
                if (point.X >= 0 && point.X <= DragHandle.ActualWidth &&
                    point.Y >= 0 && point.Y <= DragHandle.ActualHeight)
                {
                    DragHandle_MouseLeftButtonDown(DragHandle, e);
                    return;
                }
                var head = e.GetPosition(this);
                _lastHeadTouchPoint = head;
                if (_sleepAction != null)
                {
                    e.Handled = true;
                    var x = head.X / ActualWidth;
                    var y = head.Y / ActualHeight;
                    if (x >= 0.06 && x <= 0.58 && y >= 0.36 && y <= 0.96)
                        TouchSleepingHead();
                    return;
                }
                if (_main != null && TryGetFrontTouch(head, out var touchHead))
                {
                    e.Handled = true;
                    PlayTouch(touchHead, head);
                }
            }), true);

            PreviewMouseRightButtonDown += (_, e) => e.Handled = true;
            PreviewMouseRightButtonUp += (_, e) =>
            {
                // The core's default toolbar contains game systems this pet does not use.
                e.Handled = true;
                ShowPanel();
            };
        }

        private async void PetWindow_Loaded(object sender, RoutedEventArgs e)
        {
            // 发布包只带唯一内容；这里在后台还原成引擎可直接读取的目录树。
            var modDir = new DirectoryInfo(await Task.Run(() => AssetStore.Prepare(AppContext.BaseDirectory)));
            if (!File.Exists(Path.Combine(modDir.FullName, "info.lps")))
                throw new FileNotFoundException("没有找到角色素材，请重新打开完整的大卡猫程序。");
            var petInfo = new LpsDocument(File.ReadAllText(Path.Combine(modDir.FullName, "info.lps")));
            var petLoader = new PetLoader(petInfo, modDir);
            ConfigureTouchSplit(Path.Combine(modDir.FullName, "pet", "dakamao",
                "default", "breathe_b", "frame_01.png"));

            GraphCore.CachePath = Path.Combine(App.DataDirectory, "cache",
                AssetStore.GetCacheKey(Path.Combine(modDir.FullName, "pet")));

            // Match the rebuilt source tiles so the engine does not resample
            // them while assembling its atlas. Layout remains 500 logical units.
            Core.Graph = petLoader.Graph(512, Dispatcher);

            // Main 是 VPet 的核心显示控件：自带鼠标摸头/摸身、拖拽等事件处理
            _main = new MainDisplay(Core) { Width = 500, Height = 500 };
            InitializeFluidPlayback(modDir.FullName);
            _main.GraphDisplayHandler += graph =>
            {
                Dispatcher.BeginInvoke(() => DisplayAutomaticSmooth(graph), DispatcherPriority.Render);
                if ((graph.Type == GraphType.Touch_Head || graph.Type == GraphType.Touch_Body) &&
                    graph.Animat == AnimatType.A_Start)
                {
                    App.WriteLog("TOUCH " + graph.Name);
                    Dispatcher.BeginInvoke(PlayGhostHand, DispatcherPriority.Render);
                }
            };
            _main.Load_0_BaseConsole();
            // Keep head and body touch areas; dragging is owned by the visible handle.
            Core.TouchEvent.Add(new TouchArea(Core.Graph.GraphConfig.TouchHeadLocate,
                Core.Graph.GraphConfig.TouchHeadSize, () =>
                {
                    if (_sleepAction != null) TouchSleepingHead();
                    else PlayTouchAtCursor();
                    return true;
                }));
            Core.TouchEvent.Add(new TouchArea(Core.Graph.GraphConfig.TouchBodyLocate,
                Core.Graph.GraphConfig.TouchBodySize, () =>
                {
                    if (_sleepAction == null) PlayTouchAtCursor();
                    return true;
                }));
            await _main.Load_2_WaitGraph();
            foreach (var element in Core.Graph.CommUIElements.Values)
                RenderOptions.SetBitmapScalingMode(element, BitmapScalingMode.HighQuality);
            // VPet interprets the last filename number as milliseconds. The art
            // workflow uses frame_01.png for ordering, so use the shared timing
            // manifest instead of the filename for playback speed.
            foreach (var animation in Core.Graph.GraphsList.Values.SelectMany(x => x.Values).SelectMany(x => x).OfType<PNGAnimation>())
            {
                var duration = FrameDuration(animation.GraphInfo.Name,
                    animation.GraphInfo.Type.ToString().ToLowerInvariant(), animation.GraphInfo.Animat.ToString());
                // The upstream atlas contains N tiles but reports N+1 widths.
                // Correct it so every 500-unit offset lands on exactly one tile.
                animation.Width = 500 * animation.Animations.Count;
                var frameIndex = 0;
                var folder = AnimationTiming.RootElement.GetProperty("frame_ms").TryGetProperty(animation.GraphInfo.Name + "/" + animation.GraphInfo.Animat, out var customTimes)
                    ? customTimes : default;
                var timedFrames = folder.ValueKind == JsonValueKind.Array ? folder.GetArrayLength() : 0;
                foreach (var frame in animation.Animations)
                {
                    // 配置被改短时退回整段时长，避免索引越界导致启动失败。
                    frame.Time = frameIndex < timedFrames ? folder[frameIndex].GetInt32() : duration;
                    frameIndex++;
                }
            }
            if (Core.Graph.FindGraph(Core.Graph.FindName(GraphType.Default), AnimatType.Single, Core.Save.Mode) == null)
                throw new InvalidDataException("缺少待机动画定义，请检查角色包中的 info.lps。");
            _main.Load_3_BindingTimer();
            _main.Load_4_Start();
            BuildActionRing();
            App.WriteLog("RENDER source=512 cache=512 scaling=HighQuality atlas=exact_tiles blink_ms=10 touch_ms=45");
            App.WriteLog("ASSETS loaded=" + Directory.GetFiles(modDir.FullName, "frame_*.png", SearchOption.AllDirectories).Length);
            _petReady = true;
        }

        private static JsonDocument LoadAnimationTiming()
        {
            using var stream = typeof(PetWindow).Assembly.GetManifestResourceStream("DakamaoPet.animation_timing.json")
                ?? throw new InvalidDataException("缺少动画时长配置。");
            return JsonDocument.Parse(stream);
        }

        private static int FrameDuration(string name, string graphType, string phase)
        {
            var config = AnimationTiming.RootElement;
            if (config.TryGetProperty("phase_ms", out var phases) &&
                phases.TryGetProperty(name, out var actionPhases) && actionPhases.TryGetProperty(phase, out var phaseTime))
                return phaseTime.GetInt32();
            if (config.GetProperty("name_ms").TryGetProperty(name, out var named))
                return named.GetInt32();
            if (config.GetProperty("graph_type_ms").TryGetProperty(graphType, out var category))
                return category.GetInt32();
            return config.GetProperty("default_ms").GetInt32();
        }

        private void ConfigureTouchSplit(string path)
        {
            var source = BitmapFrame.Create(new Uri(path), BitmapCreateOptions.None, BitmapCacheOption.OnLoad);
            var bitmap = new FormatConvertedBitmap(source, PixelFormats.Bgra32, null, 0);
            var stride = bitmap.PixelWidth * 4;
            var pixels = new byte[stride * bitmap.PixelHeight];
            bitmap.CopyPixels(pixels, stride, 0);
            var left = bitmap.PixelWidth;
            var top = bitmap.PixelHeight;
            var right = 0;
            var bottom = 0;
            for (var y = 0; y < bitmap.PixelHeight; y++)
                for (var x = 0; x < bitmap.PixelWidth; x++)
                    if (pixels[y * stride + x * 4 + 3] >= 128)
                    {
                        left = Math.Min(left, x);
                        top = Math.Min(top, y);
                        right = Math.Max(right, x + 1);
                        bottom = Math.Max(bottom, y + 1);
                    }
            _frontTouchBounds = new Rect((double)left / bitmap.PixelWidth,
                (double)top / bitmap.PixelHeight, (double)(right - left) / bitmap.PixelWidth,
                (double)(bottom - top) / bitmap.PixelHeight);
            _frontTouchSplit = (top + bottom) / (2.0 * bitmap.PixelHeight);
            App.WriteLog($"TOUCH_SPLIT top={_frontTouchBounds.Top:F4} middle={_frontTouchSplit:F4} bottom={_frontTouchBounds.Bottom:F4}");
        }

        private bool TryGetFrontTouch(Point click, out bool head)
        {
            var normalized = new Point(click.X / ActualWidth, click.Y / ActualHeight);
            head = normalized.Y < _frontTouchSplit;
            return _frontTouchBounds.Contains(normalized);
        }

        private void PlayTouchAtCursor()
        {
            var click = Mouse.GetPosition(this);
            if (TryGetFrontTouch(click, out var head))
                PlayTouch(head, click);
        }

        private Point GetCursorScreenPoint()
        {
            GetCursorPos(out var cursor);
            var source = PresentationSource.FromVisual(this);
            return source?.CompositionTarget?.TransformFromDevice.Transform(new Point(cursor.X, cursor.Y))
                ?? new Point(cursor.X, cursor.Y);
        }

        private void PlayGhostHand()
        {
            // The fingertips of the palm-down silhouette land on the actual click.
            var click = _lastHeadTouchPoint;
            if (click.X == 0 && click.Y == 0)
                click = Mouse.GetPosition(this);
            GhostHandLayer.Margin = new Thickness(
                Math.Clamp(click.X - 43, 0, Math.Max(0, ActualWidth - GhostHandLayer.Width)),
                Math.Clamp(click.Y - 88, 0, Math.Max(0, ActualHeight - GhostHandLayer.Height)),
                0, 0);
            App.WriteLog($"GHOST_HAND click={click.X:0},{click.Y:0} left={GhostHandLayer.Margin.Left:0} top={GhostHandLayer.Margin.Top:0}");
            var opacity = new DoubleAnimationUsingKeyFrames
            {
                RepeatBehavior = new RepeatBehavior(3)
            };
            opacity.KeyFrames.Add(new LinearDoubleKeyFrame(0, KeyTime.FromTimeSpan(TimeSpan.Zero)));
            opacity.KeyFrames.Add(new LinearDoubleKeyFrame(0.8, KeyTime.FromTimeSpan(TimeSpan.FromMilliseconds(165))));
            opacity.KeyFrames.Add(new LinearDoubleKeyFrame(0.8, KeyTime.FromTimeSpan(TimeSpan.FromMilliseconds(765))));
            opacity.KeyFrames.Add(new LinearDoubleKeyFrame(0, KeyTime.FromTimeSpan(TimeSpan.FromMilliseconds(960))));
            var stroke = new DoubleAnimation(-7, 13, TimeSpan.FromMilliseconds(480))
            {
                AutoReverse = true,
                RepeatBehavior = new RepeatBehavior(3),
                EasingFunction = new SineEase { EasingMode = EasingMode.EaseInOut }
            };
            var tilt = new DoubleAnimation(174, 186, TimeSpan.FromMilliseconds(480))
            {
                AutoReverse = true,
                RepeatBehavior = new RepeatBehavior(3)
            };
            GhostHandLayer.BeginAnimation(UIElement.OpacityProperty, opacity);
            GhostHandShift.BeginAnimation(TranslateTransform.YProperty, stroke);
            GhostHandTilt.BeginAnimation(RotateTransform.AngleProperty, tilt);
        }

        private void DragHandle_MouseLeftButtonDown(object sender, MouseButtonEventArgs e)
        {
            e.Handled = true;
            if (!_petReady)
                return;
            CancelWalk();
            StopPreview(false);
            CancelSleep();
            CancelFall();
            _handleDragging = true;
            _dragCursorStart = GetCursorScreenPoint();
            _dragWindowStart = new Point(Left, Top);
            _lastDragCursor = _dragCursorStart;
            _lastDragMoveTicks = Stopwatch.GetTimestamp();
            _swayTarget = 0;
            _swayLargestLeft = 0;
            _swayLargestRight = 0;
            StartSwayTimer();
            DragHandle.CaptureMouse();
            DisplayNamedAnimation("raised_static_hold", AnimatType.B_Loop);
            App.WriteLog("GRAB cursor=" + _dragCursorStart.X.ToString("F1") + "," +
                         _dragCursorStart.Y.ToString("F1") + " top=" + Top.ToString("F1"));
        }

        private void DragHandle_MouseMove(object sender, MouseEventArgs e)
        {
            if (!_handleDragging || e.LeftButton != MouseButtonState.Pressed)
                return;
            var cursor = GetCursorScreenPoint();
            var now = Stopwatch.GetTimestamp();
            var elapsed = Math.Clamp(Stopwatch.GetElapsedTime(_lastDragMoveTicks, now).TotalSeconds,
                                     0.008, 0.05);
            var horizontalSpeed = (cursor.X - _lastDragCursor.X) / elapsed / _petScale;
            // The suspended body lags behind the handle: rightward motion tilts it left.
            // In WPF's screen coordinates a positive angle moves the lower body left.
            _swayTarget = 22 * Math.Tanh(horizontalSpeed / 950);
            _lastDragCursor = cursor;
            _lastDragMoveTicks = now;
            Left = _dragWindowStart.X + cursor.X - _dragCursorStart.X;
            Top = _dragWindowStart.Y + cursor.Y - _dragCursorStart.Y;
            e.Handled = true;
        }

        private void DragHandle_MouseLeftButtonUp(object sender, MouseButtonEventArgs e)
        {
            e.Handled = true;
            EndHandleDrag();
        }

        private void DragHandle_LostMouseCapture(object sender, MouseEventArgs e)
        {
            EndHandleDrag();
        }

        private void EndHandleDrag()
        {
            if (!_handleDragging)
                return;
            _handleDragging = false;
            _swayTarget = 0;
            App.WriteLog("SWAY left=" + _swayLargestLeft.ToString("F1") +
                         " right=" + _swayLargestRight.ToString("F1"));
            DragHandle.ReleaseMouseCapture();
            StartFall();
        }

        private void StartSwayTimer()
        {
            if (_swayTimer == null)
            {
                _swayTimer = new DispatcherTimer(DispatcherPriority.Render)
                {
                    Interval = TimeSpan.FromMilliseconds(16)
                };
                _swayTimer.Tick += (_, _) =>
                {
                    var elapsed = Math.Min(_swayClock.Elapsed.TotalSeconds, 0.04);
                    _swayClock.Restart();
                    if (_handleDragging &&
                        Stopwatch.GetElapsedTime(_lastDragMoveTicks).TotalMilliseconds > 180)
                        _swayTarget = 0;
                    _swayVelocity += (_swayTarget - _swayAngle) * 260 * elapsed;
                    _swayVelocity *= Math.Exp(-20 * elapsed);
                    _swayAngle = Math.Clamp(_swayAngle + _swayVelocity * elapsed, -24, 24);
                    _swayLargestLeft = Math.Max(_swayLargestLeft, _swayAngle);
                    _swayLargestRight = Math.Min(_swayLargestRight, _swayAngle);
                    PetSway.Angle = _swayAngle;
                    if (!_handleDragging && Math.Abs(_swayAngle) < 0.05 &&
                        Math.Abs(_swayVelocity) < 0.1)
                    {
                        PetSway.Angle = 0;
                        _swayAngle = 0;
                        _swayVelocity = 0;
                        _swayTimer?.Stop();
                        _swayClock.Stop();
                    }
                };
            }
            _swayClock.Restart();
            _swayTimer.Start();
        }

        private void StartFall()
        {
            if (_main == null)
                return;
            CancelFall();
            var sequence = ++_fallSequence;
            _falling = true;
            var floor = GetDesktopWorkArea().Bottom - ActualHeight;
            App.WriteLog("FALL floor=" + floor.ToString("F1") + " top=" + Top.ToString("F1"));
            if (Top >= floor - 2)
            {
                Top = floor;
                StartLanding(sequence);
                return;
            }

            PlayFalling(sequence);
            _fallSpeed = 80;
            _fallClock.Restart();
            _fallTimer = new DispatcherTimer(DispatcherPriority.Render)
            {
                Interval = TimeSpan.FromMilliseconds(16)
            };
            _fallTimer.Tick += FallTimer_Tick;
            _fallTimer.Start();
        }

        private void PlayFalling(int sequence)
        {
            DisplayNamedAnimation("falling", AnimatType.Single, () =>
            {
                if (_falling && sequence == _fallSequence)
                    PlayFalling(sequence);
            });
        }

        private void FallTimer_Tick(object? sender, EventArgs e)
        {
            var elapsed = Math.Min(_fallClock.Elapsed.TotalSeconds, 0.05);
            _fallClock.Restart();
            var floor = GetDesktopWorkArea().Bottom - ActualHeight;
            _fallSpeed = Math.Min(_fallSpeed + 1400 * elapsed, 1250);
            Top += _fallSpeed * elapsed;
            if (Top >= floor)
            {
                Top = floor;
                StartLanding(_fallSequence);
            }
        }

        private void StartLanding(int sequence)
        {
            _fallTimer?.Stop();
            _fallTimer = null;
            _fallClock.Stop();
            _falling = false;
            _landing = true;
            App.WriteLog("LAND top=" + Top.ToString("F1"));
            DisplayNamedAnimation("land", AnimatType.Single, () =>
            {
                if (_landing && sequence == _fallSequence)
                {
                    _landing = false;
                    FinishAction();
                }
            });
        }

        private void CancelFall()
        {
            _fallTimer?.Stop();
            _fallTimer = null;
            _fallClock.Stop();
            _falling = false;
            _landing = false;
            _fallSequence++;
        }

        private const uint MonitorDefaultToNearest = 2;

        private Rect GetDesktopWorkArea()
        {
            var source = PresentationSource.FromVisual(this);
            var window = new WindowInteropHelper(this).Handle;
            if (source?.CompositionTarget == null || window == IntPtr.Zero)
                return SystemParameters.WorkArea;
            var monitor = MonitorFromWindow(window, MonitorDefaultToNearest);
            var info = new MonitorInfo { Size = Marshal.SizeOf<MonitorInfo>() };
            if (monitor == IntPtr.Zero || !GetMonitorInfo(monitor, ref info))
                return SystemParameters.WorkArea;
            var transform = source.CompositionTarget.TransformFromDevice;
            var topLeft = transform.Transform(new Point(info.Work.Left, info.Work.Top));
            var bottomRight = transform.Transform(new Point(info.Work.Right, info.Work.Bottom));
            return new Rect(topLeft, bottomRight);
        }

        // ---------- IController：VPet 通过它移动窗口、判断屏幕边界 ----------

        public void MoveWindows(double X, double Y)
        {
            Left += X * ZoomRatio;
            Top += Y * ZoomRatio;
        }

        public double GetWindowsDistanceLeft() => Left;

        public double GetWindowsDistanceUp() => Top;

        public double GetWindowsDistanceRight() => GetDesktopWorkArea().Right - (Left + ActualWidth);

        public double GetWindowsDistanceDown() => GetDesktopWorkArea().Bottom - (Top + ActualHeight);

        public double ZoomRatio => ActualWidth / 500.0;

        public int PressLength => 600;

        public void ShowPanel()
        {
            if (ActionRing.IsOpen)
            {
                ActionRing.IsOpen = false;
                return;
            }

            if (!_actionRingReady)
                BuildActionRing();

            if (!_actionRingReady)
                return;
            RenderRingActions();
            var work = GetDesktopWorkArea();
            const double size = 160;
            const double overlap = 48;
            var besideLeft = Left - size + overlap;
            var besideRight = Left + ActualWidth - overlap;
            var horizontal = besideLeft >= work.Left ? besideLeft
                : besideRight + size <= work.Right ? besideRight
                : Math.Max(work.Left, Math.Min(Left, work.Right - size));
            ActionRing.PlacementTarget = this;
            ActionRing.HorizontalOffset = horizontal;
            ActionRing.VerticalOffset = Math.Max(work.Top,
                Math.Min(Top + (ActualHeight - size) / 2, work.Bottom - size));
            ActionRing.IsOpen = true;
            App.WriteLog("MENU opened");
        }

        private void BuildActionRing()
        {
            if (_actionRingReady || _main == null)
                return;

            var animations = Core.Graph.GraphsList.Values
                .SelectMany(group => group.Values)
                .SelectMany(group => group)
                .OfType<PNGAnimation>()
                .DistinctBy(animation => (animation.GraphInfo.Type,
                                          animation.GraphInfo.Name,
                                          animation.GraphInfo.Animat))
                .ToList();
            foreach (var action in animations.GroupBy(item => item.GraphInfo.Name))
                _previewActions[action.Key] = action.OrderBy(item => item.GraphInfo.Animat).ToList();
            RingCenterButton.Click += (_, _) =>
            {
                ActionRing.IsOpen = false;
                if (_sleepAction != null)
                    WakeSleep();
                else if (_walking)
                    StopWalk();
                else if (_previewSequence != null)
                    RequestSmoothAction(() => StopPreview());
            };
            ActionRing.PreviewKeyDown += (_, e) =>
            {
                if (e.Key == Key.Escape)
                {
                    ActionRing.IsOpen = false;
                    e.Handled = true;
                }
            };
            ActionRing.Opened += (_, _) => Dispatcher.BeginInvoke(
                new Action(() => RingCenterButton.Focus()), DispatcherPriority.Input);
            _actionRingReady = true;
            App.WriteLog($"MENU actions=6 registered={animations.Count}");
        }

        private void RenderRingActions()
        {
            RingButtons.Children.Clear();
            var entries = new (string Key, string Label)[]
            {
                ("__walk", "散步"), ("touch_head", "摸头"),
                ("touch_body_touch", "摸身"), ("idel_yawn", "哈欠"),
                ("__exit", "退出"), ("idel_sleep", "睡觉"),
                ("idel_blink", "眨眼"), ("__size", "大小"),
                ("__settings", "设定"), ("__notice", "声明"),
                ("__home", "主屏")
            };
            var playing = _previewSequence != null || _sleepAction != null || _walking;
            RingCenterButton.Content = playing ? "停止" : "收起";
            System.Windows.Automation.AutomationProperties.SetName(
                RingCenterButton, playing ? "停止播放当前动作" : "收起面板");
            for (var index = 0; index < entries.Length; index++)
            {
                var (key, label) = entries[index];
                if (!key.StartsWith("__") && key != "touch_head" && !_previewActions.ContainsKey(key))
                    continue;
                var button = new Button
                {
                    Content = label,
                    Width = 36,
                    Height = 24,
                    Style = (Style)FindResource("RingActionButtonStyle"),
                    ToolTip = key.StartsWith("__") ? null : "播放完整动作"
                };
                System.Windows.Automation.AutomationProperties.SetName(button,
                    key.StartsWith("__") ? label : label + "，播放完整动作");
                var angle = (-90 + index * 360.0 / entries.Length) * Math.PI / 180;
                Canvas.SetLeft(button, 80 + 60 * Math.Cos(angle) - button.Width / 2);
                Canvas.SetTop(button, 80 + 60 * Math.Sin(angle) - button.Height / 2);
                button.Click += (_, _) => SelectRingAction(key);
                RingButtons.Children.Add(button);
            }
        }

        private void SelectRingAction(string key)
        {
            ActionRing.IsOpen = false;
            if (key == "__settings") { ShowSettingsPage(); return; }
            if (key == "__notice") { ShowDeclarationPage(); return; }
            if (key == "__exit")
            {
                Application.Current.Shutdown();
                return;
            }
            if (key == "__size")
            {
                ShowSizePopup();
                return;
            }
            if (key == "__home")
            {
                MoveToPrimaryScreen();
                return;
            }
            if (key == "__walk")
            {
                if (_sleepAction != null)
                    WakeSleep(() => RequestSmoothAction(StartWalk));
                else
                    RequestSmoothAction(StartWalk);
                return;
            }
            if (key == "idel_sleep")
            {
                RequestSmoothAction(StartSleep);
                return;
            }
            if (key == "touch_head" && _sleepAction != null)
            {
                _lastHeadTouchPoint = new Point(ActualWidth * 0.32, ActualHeight * 0.64);
                TouchSleepingHead();
                return;
            }
            if (_sleepAction != null)
            {
                WakeSleep(() => SelectRingAction(key));
                return;
            }
            if (key == "touch_head")
            {
                var variants = new[] { "touch_head_touch", "touch_head_purr" }
                    .Where(_previewActions.ContainsKey).ToList();
                if (variants.Count > 0)
                {
                    var stages = _previewActions[variants[Random.Shared.Next(variants.Count)]];
                    RequestSmoothAction(() =>
                    {
                        _lastHeadTouchPoint = new Point(ActualWidth / 2, ActualHeight * 172 / 320);
                        PlayPreviewSequence(stages);
                    });
                }
            }
            else if (_previewActions.TryGetValue(key, out var stages))
            {
                RequestSmoothAction(() =>
                {
                    if (stages[0].GraphInfo.Type == GraphType.Touch_Body)
                        _lastHeadTouchPoint = new Point(ActualWidth / 2, ActualHeight * 0.82);
                    PlayPreviewSequence(stages);
                });
            }
        }

        private void PlayTouch(bool head, Point click)
        {
            RequestSmoothAction(() =>
            {
                _lastHeadTouchPoint = click;
                var key = head
                    ? (Random.Shared.Next(2) == 0 ? "touch_head_touch" : "touch_head_purr")
                    : "touch_body_touch";
                if (_previewActions.TryGetValue(key, out var stages))
                    PlayPreviewSequence(stages);
            });
        }

        private void RequestSmoothAction(Action action)
        {
            if (_walking)
            {
                StopWalk(action);
                return;
            }
            if (_previewSequence != null || _falling || _landing)
            {
                // Keep the latest request and finish the existing return poses.
                // Every completed sequence ends on the same neutral drawing.
                _pendingAction = action;
                App.WriteLog("TRANSITION queued");
                return;
            }
            action();
        }

        private void FinishAction()
        {
            var next = _pendingAction;
            StopPreview(false);
            if (next != null)
            {
                App.WriteLog("TRANSITION next_after_settle");
                next();
            }
            else
            {
                DisplayNormal();
                _main?.EventTimer.Start();
            }
        }

        private void PlayPreviewSequence(System.Collections.Generic.IEnumerable<PNGAnimation> animations)
        {
            if (_main == null)
                return;
            StopPreview(false);
            CancelSleep(false);
            CancelFall();
            _main.EventTimer.Stop();
            _previewSequence = animations.ToList();
            _previewIndex = 0;
            PlayNextPreviewStage();
        }

        private void PlayNextPreviewStage()
        {
            if (_main == null || _previewSequence == null)
                return;
            if (_previewIndex >= _previewSequence.Count)
            {
                FinishAction();
                return;
            }
            var animation = _previewSequence[_previewIndex++];
            var duration = Math.Max(1, animation.Animations.Sum(frame => frame.Time));
            var generation = _previewGeneration;
            var stageIndex = _previewIndex;
            var graph = animation.GraphInfo;
            App.WriteLog($"PREVIEW {graph.Name}/{graph.Animat} frames={animation.Animations.Count} duration={duration} loop={animation.IsLoop}");
            void Advance()
            {
                Dispatcher.BeginInvoke(() =>
                {
                    if (_previewGeneration == generation && _previewSequence != null &&
                        _previewIndex == stageIndex)
                    {
                        App.WriteLog($"PREVIEW_END {graph.Name}/{graph.Animat}");
                        PlayNextPreviewStage();
                    }
                }, DispatcherPriority.Render);
            }
            DisplayAnimation(animation, animation.IsLoop ? null : Advance);
            if (animation.IsLoop)
            {
                var timer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(duration) };
                timer.Tick += (_, _) =>
                {
                    if (_previewTimer != timer)
                        return;
                    timer.Stop();
                    _previewTimer = null;
                    Advance();
                };
                _previewTimer = timer;
                timer.Start();
            }
        }

        private void StopPreview(bool returnToNormal = true)
        {
            StopFluidPlayback();
            _previewTimer?.Stop();
            _previewTimer = null;
            _previewSequence = null;
            _previewIndex = 0;
            _previewGeneration++;
            _pendingAction = null;
            if (returnToNormal)
            {
                _main?.EventTimer.Start();
                DisplayNormal();
            }
        }

        private void StartSleep()
        {
            if (_main == null)
                return;
            if (_sleepAction != null)
            {
                SwitchSleepPose();
                return;
            }
            StopPreview(false);
            CancelFall();
            _sleepAction = _nextSleepBellyUp ? "sleep_belly" : "sleep_curled";
            _nextSleepBellyUp = !_nextSleepBellyUp;
            _sleepReady = false;
            _sleepGeneration++;
            // Sleep is held until another action is chosen; random idle events
            // must not replace its pose or interrupt a head response.
            _main.EventTimer.Stop();
            void Ready()
            {
                _sleepReady = true;
                HoldSleepPose();
            }
            // Reuse the exact flip sequence on entry, exit and pose changes.
            // Separate atlas stages allow dense flip frames without exceeding
            // the engine's width limit or shortening the standing transition.
            DisplaySleepStage("sleep_curled", AnimatType.A_Start, () =>
            {
                if (_sleepAction == "sleep_belly")
                    DisplaySleepStage("sleep_roll_to_belly", AnimatType.Single, Ready);
                else
                    Ready();
            });
        }

        private void HoldSleepPose()
        {
            if (_sleepWakeRequested)
                WakeSleep(_afterSleepWake);
            else if (_sleepSwitchRequested)
                SwitchSleepPose();
            else
                DisplaySleepStage(_sleepAction!, AnimatType.B_Loop);
        }

        private void SwitchSleepPose()
        {
            if (_sleepAction == null)
                return;
            if (_sleepWaking)
            {
                _afterSleepWake = StartSleep;
                return;
            }
            if (!_sleepReady || _sleepResponding)
            {
                _sleepSwitchRequested = true;
                _sleepWakeRequested = false;
                _afterSleepWake = null;
                return;
            }
            _sleepSwitchRequested = false;
            var toBelly = _sleepAction == "sleep_curled";
            var target = toBelly ? "sleep_belly" : "sleep_curled";
            _sleepReady = false;
            _sleepGeneration++;
            DisplaySleepStage(toBelly ? "sleep_roll_to_belly" : "sleep_roll_to_curled",
                AnimatType.Single, () =>
                {
                    _sleepAction = target;
                    _nextSleepBellyUp = target == "sleep_curled";
                    _sleepReady = true;
                    HoldSleepPose();
                });
        }

        private void TouchSleepingHead()
        {
            if (_sleepAction == null || !_sleepReady || _sleepResponding)
                return;
            _sleepResponding = true;
            PlayGhostHand();
            DisplaySleepStage(_sleepAction + "_touch", AnimatType.Single, () =>
            {
                _sleepResponding = false;
                HoldSleepPose();
            });
        }

        private void WakeSleep(Action? after = null)
        {
            if (_sleepAction == null || _main == null)
            {
                after?.Invoke();
                return;
            }
            if (_sleepWaking)
            {
                _afterSleepWake = after;
                return;
            }
            if (!_sleepReady || _sleepResponding)
            {
                _sleepWakeRequested = true;
                _sleepSwitchRequested = false;
                _afterSleepWake = after;
                App.WriteLog("SLEEP wake_after_settle");
                return;
            }
            _sleepWakeRequested = false;
            _sleepWaking = true;
            _afterSleepWake = after;
            _sleepGeneration++;
            _sleepReady = false;
            _sleepResponding = false;
            void CompleteWake()
            {
                var next = _afterSleepWake;
                CancelSleep(false);
                if (next == null)
                {
                    DisplayNormal();
                    _main.EventTimer.Start();
                }
                else
                    next();
            }
            if (_sleepAction == "sleep_belly")
                DisplaySleepStage("sleep_roll_to_curled", AnimatType.Single,
                    () => DisplaySleepStage("sleep_curled", AnimatType.C_End, CompleteWake));
            else
                DisplaySleepStage("sleep_curled", AnimatType.C_End, CompleteWake);
        }

        private void CancelSleep(bool resumeIdle = true)
        {
            if (_sleepAction == null)
                return;
            _sleepGeneration++;
            _sleepAction = null;
            _sleepReady = false;
            _sleepResponding = false;
            if (resumeIdle) _main?.EventTimer.Start();
            _sleepWakeRequested = false;
            _sleepSwitchRequested = false;
            _sleepWaking = false;
            _afterSleepWake = null;
        }

        private void DisplaySleepStage(string name, AnimatType stage, Action? after = null)
        {
            if (_main == null || !_previewActions.TryGetValue(name, out var animations))
                throw new InvalidDataException("缺少睡眠动画：" + name);
            var animation = animations.First(item => item.GraphInfo.Animat == stage);
            var generation = _sleepGeneration;
            App.WriteLog($"SLEEP {name}/{stage} frames={animation.Animations.Count}");
            DisplayAnimation(animation, after == null ? null : () =>
                Dispatcher.BeginInvoke(() =>
                {
                    if (_sleepGeneration == generation && _sleepAction != null)
                        after();
                }, DispatcherPriority.Render));
        }

        public bool CheckPosition() => false;

        public void ResetPosition()
        {
        }

        public bool EnableFunction => false; // 关闭数值/养成逻辑，纯展示交互

        public int InteractionCycle => 60;

        // 注意：接口成员拼写就是 RePostionActive（官方包里的笔误），照抄才能实现接口
        public bool RePostionActive { get; set; }
    }
}
