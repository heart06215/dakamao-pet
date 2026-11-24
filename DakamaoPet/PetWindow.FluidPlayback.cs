// SPDX-License-Identifier: CC-BY-NC-SA-4.0
// 新增贡献的许可范围见《项目开发文档》；不替上游角色形象授予 CC 权利。
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using VPet_Simulator.Core;
using static VPet_Simulator.Core.GraphInfo;

namespace DakamaoPet;

public partial class PetWindow
{
    private sealed class FluidSequence
    {
        public string Path { get; set; } = "";
        [JsonPropertyName("frame_ms")] public int FrameMs { get; set; }
        [JsonPropertyName("duration_ms")] public int DurationMs { get; set; }
        [JsonPropertyName("frame_durations")] public int[]? FrameDurations { get; set; }
        public string Source { get; set; } = "fluid";
        public int Count { get; set; }
    }
    private sealed class FluidRun
    {
        public string Key = "";
        public readonly CancellationTokenSource Cancel = new();
        public readonly ConcurrentDictionary<int,BitmapSource> Frames = new();
        public readonly Stopwatch Clock = new();
        public volatile int RequestedIndex;
        public int BufferLimit = 24;
    }
    private Dictionary<string,FluidSequence> _fluidSequences = new();
    private string _fluidRoot = "";
    private string _modRoot = "";
    private Image? _fluidImage;
    private FluidRun? _fluidRun;
    private EventHandler? _fluidRendering;

    // 已解码帧在多个循环之间复用。翻身序列内存占用大，单独走 96 帧滚动缓存，
    // 不进入这里；长序列（>100 帧）仍按需流式解码，避免常驻数百 MB。
    private readonly Dictionary<string,Dictionary<int,BitmapSource>> _fluidCache = new();
    private readonly Queue<string> _fluidCacheOrder = new();
    private readonly object _fluidCacheLock = new();
    private int _fluidCachedFrames;
    private const int FluidCacheBudget = 96;
    private const int FluidCacheSequenceLimit = 100;

    private void InitializeFluidPlayback(string modRoot)
    {
        _modRoot=modRoot;
        _fluidRoot=System.IO.Path.Combine(modRoot,"fluid");
        var manifest=System.IO.Path.Combine(_fluidRoot,"manifest.json");
        if(File.Exists(manifest))
        {
            try
            {
                _fluidSequences=JsonSerializer.Deserialize<Dictionary<string,FluidSequence>>(
                    File.ReadAllText(manifest),new JsonSerializerOptions{PropertyNameCaseInsensitive=true}) ?? new();
            }
            catch(Exception ex) when (ex is IOException or JsonException or UnauthorizedAccessException)
            {
                // 配置损坏时退回引擎图集，不要因此让整个程序起不来。
                App.WriteLog("SMOOTH manifest_invalid "+ex.Message);
                _fluidSequences=new();
            }
        }
        _fluidImage=new Image { Width=500,Height=500,Visibility=Visibility.Hidden,IsHitTestVisible=false };
        RenderOptions.SetBitmapScalingMode(_fluidImage,BitmapScalingMode.HighQuality);
        var layers=new Grid {Width=500,Height=500};
        layers.Children.Add(_main!); layers.Children.Add(_fluidImage);
        PetView.Child=layers;
        App.WriteLog($"SMOOTH sequences={_fluidSequences.Count} cadence=timeline buffer=24 roll_buffer=96 preroll=28 cache={FluidCacheBudget} renderer=decoded_pbgra32");
    }

    private void StopFluidPlayback(bool hide=false)
    {
        if(_fluidRendering!=null) CompositionTarget.Rendering-=_fluidRendering;
        _fluidRendering=null;
        _fluidRun?.Cancel.Cancel(); _fluidRun=null;
        if(hide && _fluidImage!=null) _fluidImage.Visibility=Visibility.Hidden;
        if(hide && _main!=null) _main.Opacity=1;
    }

    private void DisplayNormal()
    {
        // Retain the drawing until the normal PNG is ready, avoiding an atlas flash.
        StopFluidPlayback();
        _main?.DisplayToNomal();
    }

    private void DisplayNamedAnimation(string name,AnimatType phase,Action? after=null)
    {
        var animation=_previewActions[name].Find(a=>a.GraphInfo.Animat==phase)
            ?? throw new InvalidDataException("缺少动画阶段："+name+"/"+phase);
        DisplayAnimation(animation,after);
    }

    private void DisplayAnimation(PNGAnimation animation,Action? after=null)
    {
        if(_main==null) return;
        var key=animation.GraphInfo.Name+"/"+animation.GraphInfo.Animat;
        if(_fluidImage!=null && _fluidSequences.TryGetValue(key,out var sequence))
            StartFluidPlayback(animation,sequence,after);
        else
        {
            StopFluidPlayback(true);
            _main.Display(animation,after);
        }
    }

    private void DisplayAutomaticSmooth(GraphInfo graph)
    {
        if(!_petReady || _previewSequence!=null || _sleepAction!=null || _walking || _handleDragging || _falling || _landing) return;
        var key=graph.Name+"/"+graph.Animat;
        if(_fluidRun?.Key==key) return;
        if(_fluidSequences.ContainsKey(key) && _previewActions.TryGetValue(graph.Name,out var animations))
        {
            var animation=animations.Find(a=>a.GraphInfo.Animat==graph.Animat);
            if(animation!=null) DisplayAnimation(animation);
        }
        else StopFluidPlayback(true);
    }

    private Dictionary<int,BitmapSource>? AcquireFrameCache(string key,int count,bool isRoll)
    {
        if(isRoll || count>FluidCacheSequenceLimit) return null;
        lock(_fluidCacheLock)
        {
            if(_fluidCache.TryGetValue(key,out var existing)) return existing;
            var created=new Dictionary<int,BitmapSource>();
            _fluidCache[key]=created;
            _fluidCacheOrder.Enqueue(key);
            while(_fluidCachedFrames>FluidCacheBudget && _fluidCacheOrder.Count>0)
            {
                var oldest=_fluidCacheOrder.Dequeue();
                if(oldest==key) continue; // 当前序列本次播放期间保留
                if(_fluidCache.Remove(oldest,out var removed))
                    _fluidCachedFrames-=removed.Count;
            }
            return created;
        }
    }

    private void CacheDecodedFrame(string key,Dictionary<int,BitmapSource>? cache,int index,BitmapSource bitmap)
    {
        if(cache==null) return;
        lock(_fluidCacheLock)
        {
            if(!_fluidCache.TryGetValue(key,out var current) || !ReferenceEquals(current,cache)) return;
            if(cache.ContainsKey(index)) return;
            cache[index]=bitmap;
            _fluidCachedFrames++;
        }
    }

    private async void StartFluidPlayback(PNGAnimation animation,FluidSequence sequence,Action? after)
    {
        StopFluidPlayback();
        var run=new FluidRun { Key=animation.GraphInfo.Name+"/"+animation.GraphInfo.Animat };
        var isRoll=animation.GraphInfo.Name.StartsWith("sleep_roll_",StringComparison.Ordinal);
        run.BufferLimit=isRoll ? 96 : 24;
        var warmCount=Math.Min(sequence.Count,isRoll ? 28 : 4);
        _fluidRun=run;
        try
        {
            var root=sequence.Source=="pet" ? System.IO.Path.Combine(_modRoot,"pet","dakamao") : _fluidRoot;
            var directory=System.IO.Path.GetFullPath(System.IO.Path.Combine(root,sequence.Path));
            if(!directory.StartsWith(System.IO.Path.GetFullPath(root)+System.IO.Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase)
                || sequence.Count<1 || sequence.FrameMs<1 || sequence.DurationMs<1)
                throw new InvalidDataException("无效的流畅动画配置");
            var paths=Directory.GetFiles(directory,"frame_*.png");
            Array.Sort(paths,StringComparer.Ordinal);
            if(paths.Length!=sequence.Count) throw new InvalidDataException("动画帧数不匹配："+run.Key);
            var starts=new int[sequence.Count];
            if(sequence.FrameDurations!=null)
            {
                if(sequence.FrameDurations.Length!=sequence.Count) throw new InvalidDataException("动画时长不匹配："+run.Key);
                for(var i=1;i<starts.Length;i++) starts[i]=starts[i-1]+sequence.FrameDurations[i-1];
            }
            else for(var i=0;i<starts.Length;i++) starts[i]=i*sequence.FrameMs;
            BitmapSource Decode(int i)
            {
                // Decode and convert the pixel buffer on the worker. The render
                // thread receives ready-to-draw premultiplied pixels, not a lazy
                // PNG/URI decoder that may do conversion on its first display.
                using var stream=File.OpenRead(paths[i]);
                var decoded=BitmapDecoder.Create(stream,BitmapCreateOptions.PreservePixelFormat,BitmapCacheOption.OnLoad).Frames[0];
                var pixels=new FormatConvertedBitmap(decoded,PixelFormats.Pbgra32,null,0);
                var stride=pixels.PixelWidth*4;
                var data=new byte[stride*pixels.PixelHeight]; pixels.CopyPixels(data,stride,0);
                var bitmap=BitmapSource.Create(pixels.PixelWidth,pixels.PixelHeight,96,96,PixelFormats.Pbgra32,null,data,stride);
                bitmap.Freeze();
                return bitmap;
            }

            var cache=AcquireFrameCache(run.Key,sequence.Count,isRoll);
            if(cache!=null)
            {
                lock(_fluidCacheLock)
                    foreach(var pair in cache) run.Frames[pair.Key]=pair.Value;
            }
            var pending=new List<int>(warmCount+1);
            for(var i=0;i<warmCount;i++)
                if(!run.Frames.ContainsKey(i)) pending.Add(i);
            if(!run.Frames.ContainsKey(sequence.Count-1)) pending.Add(sequence.Count-1);
            await Task.Run(()=>
            {
                foreach(var index in pending)
                {
                    run.Cancel.Token.ThrowIfCancellationRequested();
                    var bitmap=Decode(index);
                    run.Frames[index]=bitmap;
                    CacheDecodedFrame(run.Key,cache,index,bitmap);
                }
            },run.Cancel.Token);
            if(_fluidRun!=run || run.Cancel.IsCancellationRequested) return;
            _fluidImage!.Source=run.Frames[0];
            // Keep the original engine's input surface active. Only its drawing
            // is hidden; the overlay remains IsHitTestVisible=false and adds no
            // new hit-test surface. Locked mode still skips the entire HWND.
            _fluidImage.Visibility=Visibility.Visible; _main!.Opacity=0;
            var graph=animation.GraphInfo;
            if((graph.Type==GraphType.Touch_Head || graph.Type==GraphType.Touch_Body) && graph.Animat==AnimatType.A_Start)
                PlayGhostHand();
            run.Clock.Start();
            var shown=0;
            var misses=0;
            var previous=-1;
            var lastRender=0d;
            var maxGap=0d;
            var ticks=0;
            _fluidRendering=(_,_)=>
            {
                if(_fluidRun!=run) return;
                var elapsed=run.Clock.Elapsed.TotalMilliseconds;
                if(ticks>0) maxGap=Math.Max(maxGap,elapsed-lastRender);
                lastRender=elapsed; ticks++;
                var found=Array.BinarySearch(starts,(int)elapsed);
                var index=Math.Clamp(found>=0 ? found : ~found-1,0,sequence.Count-1);
                run.RequestedIndex=index;
                if(run.Frames.TryGetValue(index,out var bitmap))
                {
                    _fluidImage.Source=bitmap;
                    if(index!=previous) { shown++; previous=index; }
                }
                else misses++;
                if(elapsed>=sequence.DurationMs)
                {
                    if(run.Frames.TryGetValue(sequence.Count-1,out var lastFrame)) _fluidImage.Source=lastFrame;
                    StopFluidPlayback();
                    App.WriteLog($"SMOOTH_END {graph.Name}/{graph.Animat} shown={shown} misses={misses} elapsed={elapsed:F0} render_fps={ticks*1000/elapsed:F1} max_gap_ms={maxGap:F1}");
                    if(after==null && (graph.Type==GraphType.Default || animation.IsLoop))
                        StartFluidPlayback(animation,sequence,null);
                    else after?.Invoke();
                }
            };
            CompositionTarget.Rendering+=_fluidRendering;
            App.WriteLog($"SMOOTH_PLAY {graph.Name}/{graph.Animat} frames={sequence.Count} duration={sequence.DurationMs} cache={(cache!=null ? "on" : "off")}");
            await Task.Run(async ()=>
            {
                var index=warmCount;
                while(index<sequence.Count-1)
                {
                    run.Cancel.Token.ThrowIfCancellationRequested();
                    var requested=run.RequestedIndex;
                    foreach(var old in run.Frames.Keys)
                        if(old<requested-2 && old!=sequence.Count-1) run.Frames.TryRemove(old,out _);
                    index=Math.Max(index,requested);
                    if(index>=sequence.Count-1) break;
                    if(run.Frames.Count>=run.BufferLimit) { await Task.Delay(4,run.Cancel.Token); continue; }
                    var bitmap=Decode(index);
                    run.Frames[index]=bitmap;
                    CacheDecodedFrame(run.Key,cache,index,bitmap);
                    index++;
                }
            },run.Cancel.Token);
        }
        catch(OperationCanceledException) { }
        catch(Exception ex)
        {
            if(_fluidRun==run)
            {
                App.WriteLog("SMOOTH fallback "+ex.Message);
                StopFluidPlayback(true); _main?.Display(animation,after);
            }
        }
    }
}
