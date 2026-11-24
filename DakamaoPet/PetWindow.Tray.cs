// SPDX-License-Identifier: CC-BY-NC-SA-4.0
// 新增贡献的许可范围见《项目开发文档》与 THIRD-PARTY-NOTICES.md。
using System;
using System.Windows;
using Forms = System.Windows.Forms;

namespace DakamaoPet;

public partial class PetWindow
{
    private Forms.NotifyIcon? _trayIcon;
    private Forms.ToolStripMenuItem? _trayTopItem;

    private void InitializeTray()
    {
        if (_trayIcon != null)
            return;
        try
        {
            var menu = new Forms.ContextMenuStrip();
            var home = new Forms.ToolStripMenuItem("显示 / 回到主屏");
            home.Click += (_, _) => Dispatcher.BeginInvoke(new Action(MoveToPrimaryScreen));
            _trayTopItem = new Forms.ToolStripMenuItem("强制置顶")
            {
                CheckOnClick = true,
                Checked = _desktopSettings.AlwaysOnTop
            };
            _trayTopItem.Click += (_, _) => Dispatcher.BeginInvoke(new Action(() =>
            {
                _desktopSettings.AlwaysOnTop = _trayTopItem.Checked;
                if (!_desktopSettings.AlwaysOnTop)
                    _desktopSettings.AllowClicks = true;
                ApplyDesktopSettings();
            }));
            var settings = new Forms.ToolStripMenuItem("设定…");
            settings.Click += (_, _) => Dispatcher.BeginInvoke(new Action(ShowSettingsPage));
            var notice = new Forms.ToolStripMenuItem("声明…");
            notice.Click += (_, _) => Dispatcher.BeginInvoke(new Action(ShowDeclarationPage));
            var exit = new Forms.ToolStripMenuItem("退出");
            exit.Click += (_, _) => Dispatcher.BeginInvoke(new Action(() => Application.Current.Shutdown()));
            menu.Items.Add(home);
            menu.Items.Add(_trayTopItem);
            menu.Items.Add(new Forms.ToolStripSeparator());
            menu.Items.Add(settings);
            menu.Items.Add(notice);
            menu.Items.Add(new Forms.ToolStripSeparator());
            menu.Items.Add(exit);

            _trayIcon = new Forms.NotifyIcon
            {
                Icon = LoadTrayIcon(),
                Text = "大卡猫",
                Visible = true,
                ContextMenuStrip = menu
            };
            _trayIcon.DoubleClick += (_, _) => Dispatcher.BeginInvoke(new Action(MoveToPrimaryScreen));
            App.WriteLog("TRAY ready");
        }
        catch (Exception ex)
        {
            App.WriteLog("TRAY disabled " + ex.Message);
            _trayIcon?.Dispose();
            _trayIcon = null;
            _trayTopItem = null;
        }
    }

    private static System.Drawing.Icon LoadTrayIcon()
    {
        try
        {
            var path = Environment.ProcessPath;
            if (!string.IsNullOrEmpty(path))
            {
                var extracted = System.Drawing.Icon.ExtractAssociatedIcon(path);
                if (extracted != null)
                    return extracted;
            }
        }
        catch (Exception ex)
        {
            App.WriteLog("TRAY icon_fallback " + ex.Message);
        }
        return System.Drawing.SystemIcons.Application;
    }

    private void CloseTray()
    {
        if (_trayIcon == null)
            return;
        try
        {
            _trayIcon.Visible = false;
            _trayIcon.Dispose();
        }
        catch (Exception ex)
        {
            App.WriteLog("TRAY dispose " + ex.Message);
        }
        _trayIcon = null;
        _trayTopItem = null;
    }
}
