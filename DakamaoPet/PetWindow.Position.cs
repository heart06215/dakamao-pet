// SPDX-License-Identifier: CC-BY-NC-SA-4.0
// 新增贡献的许可范围见《项目开发文档》与 THIRD-PARTY-NOTICES.md。
using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Windows;
using System.Windows.Threading;

namespace DakamaoPet;

public partial class PetWindow
{
    private sealed class SavedPosition
    {
        public double Left { get; set; }
        public double Top { get; set; }
    }

    private static string PositionPath => Path.Combine(App.DataDirectory, "position.json");
    private DispatcherTimer? _positionSaveTimer;
    private bool _positionReady;

    [DllImport("user32.dll")]
    private static extern IntPtr MonitorFromPoint(NativePoint point, uint flags);

    private void InitializePositionTracking()
    {
        LocationChanged += (_, _) => SchedulePositionSave();
    }

    private void RestorePosition()
    {
        var area = GetDesktopWorkArea();
        var left = Math.Max(area.Left, area.Right - ActualWidth - 24);
        var top = Math.Max(area.Top, area.Bottom - ActualHeight);
        try
        {
            if (File.Exists(PositionPath))
            {
                var saved = JsonSerializer.Deserialize<SavedPosition>(File.ReadAllText(PositionPath));
                if (saved != null && double.IsFinite(saved.Left) && double.IsFinite(saved.Top))
                {
                    left = saved.Left;
                    top = saved.Top;
                }
            }
        }
        catch (Exception ex) when (ex is IOException or JsonException or UnauthorizedAccessException)
        {
            App.WriteLog("POSITION reset_invalid_settings");
        }

        // 保存的位置可能位于已拔掉的显示器：交给系统选最近的显示器再夹紧。
        var work = GetWorkAreaForPoint(new Point(left + ActualWidth / 2, top + ActualHeight / 2));
        Left = Math.Clamp(left, work.Left, Math.Max(work.Left, work.Right - ActualWidth));
        Top = Math.Clamp(top, work.Top, Math.Max(work.Top, work.Bottom - ActualHeight));
        _positionReady = true;
        App.WriteLog($"POSITION restored left={Left:F0} top={Top:F0}");
    }

    private void SchedulePositionSave()
    {
        if (!_positionReady || !IsLoaded)
            return;
        if (_positionSaveTimer == null)
        {
            _positionSaveTimer = new DispatcherTimer(DispatcherPriority.Background)
            {
                Interval = TimeSpan.FromMilliseconds(700)
            };
            _positionSaveTimer.Tick += (_, _) =>
            {
                _positionSaveTimer.Stop();
                SavePosition();
            };
        }
        // 拖动或散步时持续触发，只有停下来 700ms 后才写盘。
        _positionSaveTimer.Stop();
        _positionSaveTimer.Start();
    }

    private void FlushPositionSave()
    {
        _positionSaveTimer?.Stop();
        if (_positionReady)
            SavePosition();
    }

    private void SavePosition()
    {
        try
        {
            Directory.CreateDirectory(App.DataDirectory);
            File.WriteAllText(PositionPath, JsonSerializer.Serialize(new SavedPosition { Left = Left, Top = Top }));
        }
        catch (IOException) { }
        catch (UnauthorizedAccessException) { }
    }

    private void MoveToPrimaryScreen()
    {
        var area = SystemParameters.WorkArea;
        Left = Math.Max(area.Left, area.Right - ActualWidth - 24);
        Top = Math.Max(area.Top, area.Bottom - ActualHeight);
        SavePosition();
        Show();
        Activate();
        App.WriteLog("POSITION moved_primary");
    }

    private Rect GetWorkAreaForPoint(Point point)
    {
        var source = PresentationSource.FromVisual(this);
        if (source?.CompositionTarget == null)
            return SystemParameters.WorkArea;
        var device = source.CompositionTarget.TransformToDevice.Transform(point);
        var monitor = MonitorFromPoint(
            new NativePoint { X = (int)Math.Round(device.X), Y = (int)Math.Round(device.Y) },
            MonitorDefaultToNearest);
        var info = new MonitorInfo { Size = Marshal.SizeOf<MonitorInfo>() };
        if (monitor == IntPtr.Zero || !GetMonitorInfo(monitor, ref info))
            return SystemParameters.WorkArea;
        var transform = source.CompositionTarget.TransformFromDevice;
        var topLeft = transform.Transform(new Point(info.Work.Left, info.Work.Top));
        var bottomRight = transform.Transform(new Point(info.Work.Right, info.Work.Bottom));
        return new Rect(topLeft, bottomRight);
    }
}
