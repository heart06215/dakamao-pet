// SPDX-License-Identifier: CC-BY-NC-SA-4.0
// 本项目有权许可的新增贡献适用；上游鸣潮/大卡猫形象的 CC 授权未确认。
// 第三方组件保留原许可，范围及公益声明见《项目开发文档》。
using System.IO;
using System.Threading;
using System.Windows;

namespace DakamaoPet
{
    public partial class App : Application
    {
        private Mutex? _instance;
        private bool _ownsInstance;

        internal static string DataDirectory => Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "DakamaoPet");

        protected override void OnStartup(StartupEventArgs e)
        {
            // Repeated double-clicks keep the existing pet instead of creating a crowd.
            _instance = new Mutex(true, @"Local\DakamaoPet.Desktop", out _ownsInstance);
            if (!_ownsInstance)
            {
                Shutdown();
                return;
            }

            DispatcherUnhandledException += (_, args) =>
            {
                WriteLog("ERROR " + args.Exception);
                args.Handled = true;
                MessageBox.Show("大卡猫启动或运行时遇到了问题。\n\n" + args.Exception.Message
                    + "\n\n日志位置：" + Path.Combine(DataDirectory, "app.log"),
                    "大卡猫", MessageBoxButton.OK, MessageBoxImage.Error);
                Shutdown(1);
            };

            Directory.CreateDirectory(DataDirectory);
            // Engine caches belong in the user's writable folder, independent of
            // where the portable EXE is stored or which shortcut launched it.
            Environment.CurrentDirectory = DataDirectory;
            WriteLog("START pid=" + Environment.ProcessId);
            base.OnStartup(e);
        }

        internal static void WriteLog(string message)
        {
            try
            {
                Directory.CreateDirectory(DataDirectory);
                File.AppendAllText(Path.Combine(DataDirectory, "app.log"),
                    DateTimeOffset.Now.ToString("O") + " " + message + Environment.NewLine);
            }
            catch (IOException) { }
            catch (UnauthorizedAccessException) { }
        }

        protected override void OnExit(ExitEventArgs e)
        {
            if (_ownsInstance)
            {
                WriteLog("EXIT code=" + e.ApplicationExitCode);
                _instance?.ReleaseMutex();
            }
            _instance?.Dispose();
            base.OnExit(e);
        }
    }
}
