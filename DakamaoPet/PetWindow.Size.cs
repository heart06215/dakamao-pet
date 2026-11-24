// SPDX-License-Identifier: CC-BY-NC-SA-4.0
// 本项目有权许可的新增贡献适用；角色形象授权记录见 THIRD-PARTY-NOTICES.md。
// 第三方组件保留原许可，范围及公益声明见《项目开发文档》。
using System;
using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Input;
using System.Windows.Controls.Primitives;
using System.Windows.Threading;
using System.Linq;

namespace DakamaoPet;

public partial class PetWindow
{
    private double _petScale = 1;
    private static readonly double[] SizeStops = { 60, 100, 160, 200, 300 };
    private bool _loadingSize = true;
    private DispatcherTimer? _sizeSaveTimer;
    private static string SizeSettingsPath => Path.Combine(App.DataDirectory, "size.json");

    private void LoadPetSize()
    {
        _loadingSize = true;
        try
        {
            if (File.Exists(SizeSettingsPath))
                _petScale = Math.Clamp(JsonSerializer.Deserialize<double>(File.ReadAllText(SizeSettingsPath)), 0.6, 3.0);
        }
        catch (Exception ex) when (ex is IOException or JsonException or UnauthorizedAccessException)
        {
            App.WriteLog("SIZE reset_invalid_settings");
        }
        if (!double.IsFinite(_petScale)) _petScale = 1;
        Width = Height = 320 * _petScale;
        SizeSlider.Value = _petScale * 100;
        SizePresets.SelectedIndex = Array.FindIndex(SizeStops, size => Math.Abs(size - _petScale * 100) < 0.01);
        SizeValueText.Text = $"大小 {_petScale:P0}";
        _loadingSize = false;
        SizeSlider.AddHandler(Thumb.DragStartedEvent, new DragStartedEventHandler((_, _) =>
            App.WriteLog($"SIZE drag_started percent={SizeSlider.Value:F0}")));
        SizeSlider.AddHandler(Thumb.DragCompletedEvent, new DragCompletedEventHandler((_, _) =>
            FlushSizeSettings()));
    }

    private void SizeSlider_ValueChanged(object sender, RoutedPropertyChangedEventArgs<double> e)
    {
        if (_loadingSize || SizeValueText == null) return;
        var center = Left + Width / 2;
        var floor = Top + Height;
        _petScale = Math.Clamp(e.NewValue / 100, 0.6, 3.0);
        Width = Height = 320 * _petScale;
        SizeValueText.Text = $"大小 {_petScale:P0}";
        if (SizePresets != null)
        {
            var preset = Array.FindIndex(SizeStops, size => Math.Abs(size - e.NewValue) < 0.01);
            SizePresets.SelectedIndex = preset;
        }
        if (IsLoaded)
        {
            var desktop = GetDesktopWorkArea();
            Left = Math.Clamp(center - Width / 2, desktop.Left, Math.Max(desktop.Left, desktop.Right - Width));
            Top = Math.Clamp(floor - Height, desktop.Top, Math.Max(desktop.Top, desktop.Bottom - Height));
            if (_walking) Top = desktop.Bottom - Height;
        }
        // 拖动滑块会连续触发；防抖后只写一次，避免每秒几十次磁盘写入。
        ScheduleSizeSave();
    }

    private void ScheduleSizeSave()
    {
        if (_sizeSaveTimer == null)
        {
            _sizeSaveTimer = new DispatcherTimer(DispatcherPriority.Background)
            {
                Interval = TimeSpan.FromMilliseconds(400)
            };
            _sizeSaveTimer.Tick += (_, _) =>
            {
                _sizeSaveTimer.Stop();
                SaveSizeNow();
            };
        }
        _sizeSaveTimer.Stop();
        _sizeSaveTimer.Start();
    }

    private void FlushSizeSettings()
    {
        _sizeSaveTimer?.Stop();
        if (_petScale > 0)
            SaveSizeNow();
    }

    private void SaveSizeNow()
    {
        try
        {
            Directory.CreateDirectory(App.DataDirectory);
            File.WriteAllText(SizeSettingsPath, JsonSerializer.Serialize(_petScale));
        }
        catch (IOException) { }
        catch (UnauthorizedAccessException) { }
        App.WriteLog($"SIZE percent={_petScale * 100:F0} window={Width:F0}x{Height:F0}");
    }

    private void ShowSizePopup()
    {
        var desktop = GetDesktopWorkArea();
        SizePopup.PlacementTarget = this;
        SizePopup.HorizontalOffset = Math.Clamp(Left + Width / 2 - 94, desktop.Left, Math.Max(desktop.Left, desktop.Right - 188));
        SizePopup.VerticalOffset = Math.Clamp(Top + 40, desktop.Top, Math.Max(desktop.Top, desktop.Bottom - 145));
        SizePopup.IsOpen = true;
    }

    private void SizePopup_Opened(object? sender, EventArgs e) => SizeSlider.Focus();
    private void ResetSize_Click(object sender, RoutedEventArgs e) => SizeSlider.Value = 100;
    private void SizePresets_SelectionChanged(object sender, System.Windows.Controls.SelectionChangedEventArgs e)
    {
        if (_loadingSize || SizePresets.SelectedIndex < 0) return;
        SizeSlider.Value = SizeStops[SizePresets.SelectedIndex];
    }
    private void SizePopup_KeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key != Key.Escape) return;
        SizePopup.IsOpen = false;
        e.Handled = true;
    }
}
