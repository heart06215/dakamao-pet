// SPDX-License-Identifier: CC-BY-NC-SA-4.0
// Project-owned contributions only. Upstream character rights remain separate.
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Interop;
using System.Windows.Media;
using DakamaoPet;
using VPet_Simulator.Core;
using static VPet_Simulator.Core.GraphInfo;

internal static class Program
{
    [DllImport("user32.dll",EntryPoint="GetWindowLongPtrW")]
    private static extern IntPtr GetWindowLongPtr(IntPtr hwnd,int index);
    private static readonly BindingFlags Private=BindingFlags.Instance|BindingFlags.NonPublic;
    private static object? Field(PetWindow window,string name)=>typeof(PetWindow).GetField(name,Private)!.GetValue(window);
    private static void Call(PetWindow window,string name,params object?[] args)=>typeof(PetWindow).GetMethod(name,Private)!.Invoke(window,args);
    private static void Assert(bool condition,string name,Dictionary<string,object> report)
    { if(!condition) throw new InvalidOperationException(name); report[name]=true; }

    [STAThread]
    public static int Main(string[] args)
    {
        var report=new Dictionary<string,object>();
        var target=Path.GetFullPath(args[0]);
        var app=new App(); app.InitializeComponent();
        app.StartupUri=new Uri("/"+typeof(App).Assembly.GetName().Name+";component/PetWindow.xaml",UriKind.Relative);
        app.Startup+=async (_,_)=>
        {
            PetWindow? window=null;
            object? settings=null;
            bool savedTop=true,savedClicks=true;
            double savedScale=1;
            byte[]? savedSize=null;
            var sizePath=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"DakamaoPet/size.json");
            try
            {
                for(var i=0;i<100;i++)
                {
                    await Task.Delay(400);
                    window=app.MainWindow as PetWindow;
                    if(window!=null && (bool)Field(window,"_petReady")!) break;
                }
                if(window==null || !(bool)Field(window,"_petReady")!) throw new Exception("Assets not ready");
                window.IsEnabled=false; // isolate the test fixture from concurrent manual drags
                settings=Field(window,"_desktopSettings")!;
                savedTop=(bool)settings.GetType().GetProperty("AlwaysOnTop")!.GetValue(settings)!;
                savedClicks=(bool)settings.GetType().GetProperty("AllowClicks")!.GetValue(settings)!;
                savedScale=(double)Field(window,"_petScale")!;
                if(File.Exists(sizePath)) savedSize=File.ReadAllBytes(sizePath);
                void Set(string property,bool value)=>settings.GetType().GetProperty(property)!.SetValue(settings,value);
                Set("AlwaysOnTop",true); Set("AllowClicks",false); Call(window,"ApplyDesktopSettings",false);
                var handle=new WindowInteropHelper(window).Handle;
                var badge=(Window)Field(window,"_unlockBadge")!;
                badge.IsEnabled=false;
                Assert(window.Topmost && (GetWindowLongPtr(handle,-20).ToInt64()&0x20)!=0,"native_click_through_enabled",report);
                Assert(badge.IsVisible && badge.Owner==window && new WindowInteropHelper(badge).Handle!=handle,"unlock_has_independent_native_window",report);
                ((Button)badge.Content).RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
                Assert((GetWindowLongPtr(handle,-20).ToInt64()&0x20)==0 && !badge.IsVisible,"unlock_button_restores_interaction",report);
                Set("AlwaysOnTop",false); Set("AllowClicks",false); Call(window,"ApplyDesktopSettings",false);
                Assert(!window.Topmost && (bool)settings.GetType().GetProperty("AllowClicks")!.GetValue(settings)!,"disabling_topmost_unlocks_pet",report);
                var slider=(Slider)window.FindName("SizeSlider"); var presets=(ComboBox)window.FindName("SizePresets");
                slider.Value=300; await Task.Delay(40);
                Assert(window.Width==960 && presets.SelectedIndex==4 && presets.Items.Count==5,"size_300_and_five_presets",report);
                presets.SelectedIndex=2; await Task.Delay(40);
                Assert(window.Width==512 && slider.Value==160,"size_160_preset",report);
                Call(window,"ShowDeclarationPage");
                var declaration=(Window)Field(window,"_declarationPage")!;
                var declarationPanel=(StackPanel)((ScrollViewer)declaration.Content).Content;
                var text=string.Join("\n",declarationPanel.Children.OfType<TextBlock>().Select(t=>t.Text));
                Assert(text.Contains("不应该以任何形式付款购买") && text.Contains("鸣潮二创形象大卡猫") && text.Contains("已获得上游形象作者授权") && text.Contains("space.bilibili.com/350988058"),"declaration_scope_and_required_text",report);
                Assert(declarationPanel.Children.OfType<TextBox>().Single().Text.StartsWith("https://github.com/"),"github_placeholder_present",report);
                declaration.Close();
                var main=(VPet_Simulator.Core.Main)Field(window,"_main")!; main.EventTimer.Stop();
                // This marker prevents random legacy idle callbacks interfering
                // with the explicitly checked high-density sequence stages.
                typeof(PetWindow).GetField("_previewSequence",Private)!.SetValue(window,new List<PNGAnimation>());
                foreach(var (name,phase) in new[] {("sleep_roll_to_belly",AnimatType.Single),("sleep_roll_to_curled",AnimatType.Single),("sleep_curled",AnimatType.C_End),("touch_head_touch",AnimatType.A_Start),("raised_static_hold",AnimatType.B_Loop),("falling",AnimatType.Single)})
                {
                    var completed=new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
                    Call(window,"DisplayNamedAnimation",name,phase,(Action)(()=>completed.TrySetResult()));
                    await completed.Task.WaitAsync(TimeSpan.FromSeconds(12));
                    Assert(((Image)Field(window,"_fluidImage")!).Source!=null,"played_"+name+"_"+phase,report);
                }
                window.IsEnabled=true;
                var hit=window.InputHitTest(new Point(window.ActualWidth*.5,window.ActualHeight*.65)) as DependencyObject;
                var belongs=false;
                while(hit!=null) { if(ReferenceEquals(hit,main)) {belongs=true;break;} hit=VisualTreeHelper.GetParent(hit); }
                Assert(belongs && main.Visibility==Visibility.Visible && main.Opacity==0,"original_input_surface_retained_during_fluid_playback",report);
                window.IsEnabled=false;
                Call(window,"StopPreview",false);
                async Task WaitForSleep()
                {
                    for(var i=0;i<150;i++)
                    {
                        await Task.Delay(100);
                        if(Field(window,"_sleepAction")!=null && (bool)Field(window,"_sleepReady")!) return;
                    }
                    throw new TimeoutException("Sleep button sequence did not settle");
                }
                Call(window,"SelectRingAction","idel_sleep");
                await WaitForSleep();
                var firstPose=(string)Field(window,"_sleepAction")!;
                var sharedImage=(Image)Field(window,"_fluidImage")!;
                Call(window,"SelectRingAction","idel_sleep");
                Assert(!(bool)Field(window,"_sleepReady")!,"second_sleep_click_starts_direct_roll",report);
                await WaitForSleep(); await Task.Delay(80);
                Assert((string)Field(window,"_sleepAction")! != firstPose,"second_sleep_click_changes_pose",report);
                Assert(ReferenceEquals(sharedImage,Field(window,"_fluidImage")) && sharedImage.Visibility==Visibility.Visible
                    && sharedImage.Source is System.Windows.Media.Imaging.BitmapSource source && source.PixelWidth==512
                    && main.Opacity==0,"static_sleep_and_roll_share_original_png_renderer",report);
                Assert(sharedImage.Source is System.Windows.Media.Imaging.BitmapSource readyPixels
                    && readyPixels.Format==PixelFormats.Pbgra32 && readyPixels.IsFrozen,
                    "render_frames_are_frozen_predecoded_pbgra32",report);
                Call(window,"SelectRingAction","idel_sleep");
                await WaitForSleep();
                Assert((string)Field(window,"_sleepAction")! == firstPose,"third_sleep_click_rolls_back",report);
                Call(window,"CancelSleep",false);
                var logDirectory=(string)typeof(App).GetProperty("DataDirectory",BindingFlags.NonPublic|BindingFlags.Static)!.GetValue(null)!;
                report["log_directory"]=logDirectory;
                report["roll_playback_samples"]=File.ReadLines(Path.Combine(logDirectory,"app.log"))
                    .Where(line=>line.Contains("SMOOTH_END sleep_roll_")).TakeLast(4).ToArray();
                report["passed"]=true;
            }
            catch(Exception ex) {report["passed"]=false;report["error"]=ex.ToString();}
            finally
            {
                if(window!=null && settings!=null)
                {
                    settings.GetType().GetProperty("AlwaysOnTop")!.SetValue(settings,savedTop);
                    settings.GetType().GetProperty("AllowClicks")!.SetValue(settings,savedClicks);
                    Call(window,"ApplyDesktopSettings",true);
                    ((Slider)window.FindName("SizeSlider")).Value=savedScale*100;
                    if(savedSize!=null) File.WriteAllBytes(sizePath,savedSize);
                    Call(window,"StopFluidPlayback",true);
                    window.IsEnabled=true;
                }
                Directory.CreateDirectory(Path.GetDirectoryName(target)!);
                File.WriteAllText(target,JsonSerializer.Serialize(report,new JsonSerializerOptions{WriteIndented=true}));
                app.Shutdown(report.TryGetValue("passed",out var passed) && passed is true ? 0:1);
            }
        };
        return app.Run();
    }
}
