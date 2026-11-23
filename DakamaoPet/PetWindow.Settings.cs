// SPDX-License-Identifier: CC-BY-NC-SA-4.0
// 仅本项目有权许可的新增贡献适用。上游鸣潮/大卡猫形象的 CC 授权未确认。
// 第三方组件保留原许可；授权范围与公益声明见《项目开发文档》。
using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Media;

namespace DakamaoPet;

public partial class PetWindow
{
    private sealed class DesktopSettings
    {
        public bool AlwaysOnTop { get; set; } = true;
        public bool AllowClicks { get; set; } = true;
    }
    private DesktopSettings _desktopSettings = new();
    private Window? _unlockBadge;
    private Window? _settingsPage;
    private Window? _declarationPage;
    private static readonly Brush PanelBackground = new SolidColorBrush(Color.FromRgb(31,48,67));
    private static readonly Brush PanelBorder = new SolidColorBrush(Color.FromRgb(213,232,244));
    private static string DesktopSettingsPath => Path.Combine(App.DataDirectory,"desktop-settings.json");

    [DllImport("user32.dll", EntryPoint="GetWindowLongPtrW", SetLastError=true)]
    private static extern IntPtr GetWindowLongPtr(IntPtr hwnd, int index);
    [DllImport("user32.dll", EntryPoint="SetWindowLongPtrW", SetLastError=true)]
    private static extern IntPtr SetWindowLongPtr(IntPtr hwnd, int index, IntPtr value);
    [DllImport("user32.dll",SetLastError=true)]
    private static extern bool SetWindowPos(IntPtr hwnd,IntPtr after,int x,int y,int width,int height,uint flags);

    private void InitializeDesktopSettings()
    {
        try
        {
            if (File.Exists(DesktopSettingsPath))
                _desktopSettings = JsonSerializer.Deserialize<DesktopSettings>(File.ReadAllText(DesktopSettingsPath)) ?? new();
        }
        catch (Exception ex) when (ex is IOException or JsonException or UnauthorizedAccessException)
        { App.WriteLog("SETTINGS reset_invalid_settings"); }
        if (!_desktopSettings.AlwaysOnTop) _desktopSettings.AllowClicks = true;
        Topmost = _desktopSettings.AlwaysOnTop;
        SourceInitialized += (_,_) => ApplyDesktopSettings(false);
        LocationChanged += (_,_) => PositionUnlockBadge();
        SizeChanged += (_,_) => PositionUnlockBadge();
    }

    private void ApplyDesktopSettings(bool save=true)
    {
        Topmost = _desktopSettings.AlwaysOnTop;
        if (!Topmost) _desktopSettings.AllowClicks = true;
        var hwnd = new WindowInteropHelper(this).Handle;
        if (hwnd == IntPtr.Zero) return;
        const long transparent = 0x20;
        var style = GetWindowLongPtr(hwnd,-20).ToInt64();
        SetWindowLongPtr(hwnd,-20,new IntPtr(_desktopSettings.AllowClicks ? style & ~transparent : style | transparent));
        SetWindowPos(hwnd,IntPtr.Zero,0,0,0,0,0x37); // refresh styles, without moving, activating or reordering
        if (!_desktopSettings.AllowClicks)
        {
            ActionRing.IsOpen = false;
            SizePopup.IsOpen = false;
            if (_handleDragging) EndHandleDrag();
            if (_unlockBadge == null)
            {
                // This is a separate HWND: the pet's WS_EX_TRANSPARENT does
                // not disable the only path back to interactive operation.
                var button = new Button
                {
                    Width=32, Height=32, ToolTip="解锁桌宠，恢复点击和拖拽",
                    Style=(Style)FindResource("RingCenterButtonStyle")
                };
                button.Content=new System.Windows.Shapes.Path
                {
                    Data=Geometry.Parse("M 7,12 V 8 C 7,1 23,1 23,8 V 12 M 4,12 H 26 V 28 H 4 Z M 15,18 V 23"),
                    Stroke=Brushes.White,StrokeThickness=2,Width=18,Height=22,Stretch=Stretch.Uniform
                };
                System.Windows.Automation.AutomationProperties.SetName(button,"解锁桌宠");
                button.Click += (_,_) =>
                {
                    _desktopSettings.AllowClicks=true;
                    ApplyDesktopSettings();
                    DragHandle.Focus();
                };
                _unlockBadge = new Window
                {
                    Owner=this, Width=32, Height=32, WindowStyle=WindowStyle.None,
                    ResizeMode=ResizeMode.NoResize, AllowsTransparency=true,
                    Background=Brushes.Transparent, ShowInTaskbar=false,
                    Topmost=true, Content=button
                };
            }
            PositionUnlockBadge();
            _unlockBadge.Show();
        }
        else _unlockBadge?.Hide();
        if (_settingsPage != null) _settingsPage.Topmost=Topmost;
        if (_declarationPage != null) _declarationPage.Topmost=Topmost;
        if (save)
        {
            Directory.CreateDirectory(App.DataDirectory);
            File.WriteAllText(DesktopSettingsPath,JsonSerializer.Serialize(_desktopSettings));
        }
        App.WriteLog($"SETTINGS topmost={Topmost} click_through={!_desktopSettings.AllowClicks}");
    }

    private void PositionUnlockBadge()
    {
        if (_unlockBadge == null) return;
        var desktop=GetDesktopWorkArea();
        _unlockBadge.Left=Math.Clamp(Left+Width/2-16,desktop.Left,Math.Max(desktop.Left,desktop.Right-32));
        _unlockBadge.Top=Math.Clamp(Top+56,desktop.Top,Math.Max(desktop.Top,desktop.Bottom-32));
    }

    private Window CreateInfoPage(string title, StackPanel content, double width)
    {
        var page = new Window
        {
            Owner=this, Title=title, Width=width, SizeToContent=SizeToContent.Height,
            MaxHeight=Math.Max(240,GetDesktopWorkArea().Height-32),
            ResizeMode=ResizeMode.NoResize, WindowStartupLocation=WindowStartupLocation.CenterOwner,
            Topmost=Topmost, Background=PanelBackground, ShowInTaskbar=false,
            FontFamily=new FontFamily("Microsoft YaHei UI"), FontSize=13,
            Content=new ScrollViewer { Content=content, VerticalScrollBarVisibility=ScrollBarVisibility.Auto }
        };
        content.Margin=new Thickness(20);
        KeyboardNavigation.SetTabNavigation(content,KeyboardNavigationMode.Cycle);
        page.PreviewKeyDown += (_,e) => { if(e.Key==Key.Escape) {page.Close();e.Handled=true;} };
        var close = new Button
        {
            Content="关闭页面", Width=100, Height=32, Margin=new Thickness(0,16,0,0),
            HorizontalAlignment=HorizontalAlignment.Left, Style=(Style)FindResource("RingActionButtonStyle")
        };
        close.Click += (_,_) => page.Close();
        content.Children.Add(close);
        page.ContentRendered += (_,_) => content.MoveFocus(new TraversalRequest(FocusNavigationDirection.First));
        page.Loaded += (_,_) =>
        {
            var desktop=GetDesktopWorkArea();
            page.Left=Math.Clamp(page.Left,desktop.Left,Math.Max(desktop.Left,desktop.Right-page.ActualWidth));
            page.Top=Math.Clamp(page.Top,desktop.Top,Math.Max(desktop.Top,desktop.Bottom-page.ActualHeight));
        };
        return page;
    }

    private static TextBlock PageText(string text, bool heading=false) => new()
    {
        Text=text, TextWrapping=TextWrapping.Wrap, Foreground=Brushes.White,
        FontSize=heading?16:13, FontWeight=heading?FontWeights.SemiBold:FontWeights.Normal,
        Margin=new Thickness(0,0,0,12), LineHeight=22
    };

    private void ShowSettingsPage()
    {
        if (_settingsPage != null) { _settingsPage.Activate(); return; }
        var panel=new StackPanel();
        panel.Children.Add(PageText("桌面交互设定",true));
        var top=new CheckBox { Content="强制置顶",IsChecked=_desktopSettings.AlwaysOnTop,Foreground=Brushes.White,MinHeight=32 };
        var clicks=new CheckBox { Content="允许点击和拖拽桌宠",IsChecked=_desktopSettings.AllowClicks,Foreground=Brushes.White,MinHeight=32,IsEnabled=_desktopSettings.AlwaysOnTop };
        panel.Children.Add(top); panel.Children.Add(clicks);
        panel.Children.Add(PageText("置顶后可关闭点击：鼠标会穿过桌宠操作下方应用。头顶图标下的锁按钮仍可点击，点击即可解锁。"));
        top.Click += (_,_) =>
        {
            _desktopSettings.AlwaysOnTop=top.IsChecked==true;
            clicks.IsEnabled=_desktopSettings.AlwaysOnTop;
            if (!_desktopSettings.AlwaysOnTop) { clicks.IsChecked=true; _desktopSettings.AllowClicks=true; }
            ApplyDesktopSettings();
        };
        clicks.Click += (_,_) =>
        {
            _desktopSettings.AllowClicks=clicks.IsChecked==true;
            ApplyDesktopSettings();
            if (!_desktopSettings.AllowClicks) _settingsPage?.Close();
        };
        _settingsPage=CreateInfoPage("大卡猫 · 设定",panel,340);
        _settingsPage.Closed += (_,_) => _settingsPage=null;
        _settingsPage.Show();
    }

    private void ShowDeclarationPage()
    {
        if (_declarationPage != null) { _declarationPage.Activate(); return; }
        var panel=new StackPanel();
        panel.Children.Add(PageText("项目声明",true));
        panel.Children.Add(PageText("该项目为公益项目，不应该以任何形式付款购买"));
        panel.Children.Add(PageText("该项目形象是基于鸣潮二创形象大卡猫的再次创作"));
        panel.Children.Add(PageText("GitHub 地址"));
        panel.Children.Add(new TextBox
        {
            Text="https://github.com/heart06215/dakamao-pet",IsReadOnly=true,
            Background=PanelBackground,Foreground=Brushes.White,BorderBrush=PanelBorder,
            Padding=new Thickness(8),Margin=new Thickness(0,0,0,12)
        });
        panel.Children.Add(PageText("本项目有权许可的新增贡献采用 CC BY-NC-SA 4.0（署名、非商业性使用、相同方式共享）。"));
        panel.Children.Add(PageText("尚未确认上游大卡猫形象作者采用 CC 协议；本声明不代替上游授权，也不授予鸣潮、上游角色形象或其他第三方内容的权利。第三方组件保留各自许可。"));
        _declarationPage=CreateInfoPage("大卡猫 · 声明",panel,420);
        _declarationPage.Closed += (_,_) => _declarationPage=null;
        _declarationPage.Show();
    }

    private void CloseDesktopSettings()
    {
        _unlockBadge?.Close(); _settingsPage?.Close(); _declarationPage?.Close();
    }
}
