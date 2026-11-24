// SPDX-License-Identifier: CC-BY-NC-SA-4.0
// 新增贡献的许可范围见《项目开发文档》与 THIRD-PARTY-NOTICES.md。
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace DakamaoPet;

/// <summary>
/// 发布包中的 PetMod 以“唯一内容 + 布局表”存放；首次启动时在用户目录
/// 还原成正常目录树。优先使用硬链接，跨卷时退回复制。开发构建没有
/// layout.json，会直接使用原始 PetMod 目录。
/// </summary>
internal static class AssetStore
{
    private sealed class AssetCacheEntry
    {
        public string Signature { get; set; } = "";
        public string Hash { get; set; } = "";
    }

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern bool CreateHardLinkW(string newFileName, string existingFileName, IntPtr securityAttributes);

    public static string Prepare(string baseDirectory)
    {
        var bundled = Path.Combine(baseDirectory, "PetMod");
        var layoutPath = Path.Combine(bundled, "layout.json");
        if (!File.Exists(layoutPath))
            return bundled;

        var layoutBytes = File.ReadAllBytes(layoutPath);
        var version = Convert.ToHexString(SHA256.HashData(layoutBytes))[..16];
        var assetsRoot = Path.Combine(App.DataDirectory, "assets");
        var target = Path.Combine(assetsRoot, version);
        var ready = Path.Combine(target, ".ready");
        if (File.Exists(ready))
        {
            App.WriteLog("ASSET_STORE reuse=" + version);
            return Path.Combine(target, "PetMod");
        }

        var clock = Stopwatch.StartNew();
        var temp = target + ".tmp-" + Environment.ProcessId;
        try
        {
            if (Directory.Exists(temp))
                Directory.Delete(temp, true);
            Directory.CreateDirectory(temp);

            var layout = JsonSerializer.Deserialize<Dictionary<string, string>>(layoutBytes)
                ?? throw new InvalidDataException("layout.json 格式无效");
            var root = Path.GetFullPath(temp);
            long linked = 0, copied = 0;
            foreach (var (logical, blob) in layout)
            {
                var destination = Path.GetFullPath(Path.Combine(root, "PetMod", logical));
                var source = Path.GetFullPath(Path.Combine(bundled, blob));
                if (!destination.StartsWith(root + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)
                    || !source.StartsWith(Path.GetFullPath(bundled) + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                    throw new InvalidDataException("layout.json 路径越界");
                Directory.CreateDirectory(Path.GetDirectoryName(destination)!);
                if (CreateHardLinkW(destination, source, IntPtr.Zero))
                    linked++;
                else
                {
                    File.Copy(source, destination, true);
                    copied++;
                }
            }

            File.WriteAllText(Path.Combine(temp, ".ready"), version + Environment.NewLine);
            Directory.CreateDirectory(assetsRoot);
            if (Directory.Exists(target))
                Directory.Delete(target, true);
            Directory.Move(temp, target);
            CleanupOldVersions(assetsRoot, version);
            App.WriteLog($"ASSET_STORE build={version} entries={layout.Count} hardlinks={linked} copies={copied} elapsed_ms={clock.ElapsedMilliseconds}");
            return Path.Combine(target, "PetMod");
        }
        catch
        {
            try { if (Directory.Exists(temp)) Directory.Delete(temp, true); } catch { }
            throw;
        }
    }

    private static void CleanupOldVersions(string assetsRoot, string current)
    {
        try
        {
            foreach (var directory in Directory.GetDirectories(assetsRoot))
            {
                if (string.Equals(Path.GetFileName(directory), current, StringComparison.OrdinalIgnoreCase))
                    continue;
                var isStaleTemp = Path.GetFileName(directory).Contains(".tmp-", StringComparison.OrdinalIgnoreCase);
                if (!isStaleTemp && !File.Exists(Path.Combine(directory, ".ready")))
                    continue;
                try { Directory.Delete(directory, true); }
                catch (IOException) { }
                catch (UnauthorizedAccessException) { }
            }
        }
        catch (IOException) { }
        catch (UnauthorizedAccessException) { }
    }

    /// <summary>
    /// 素材缓存键。先用文件数量、总字节数与最大修改时间做快速签名；
    /// 签名命中时复用上次完整内容哈希，避免每次启动读取并哈希 300+ MB PNG。
    /// </summary>
    public static string GetCacheKey(string petRoot)
    {
        var files = Directory.GetFiles(petRoot, "*.png", SearchOption.AllDirectories);
        Array.Sort(files, StringComparer.Ordinal);
        var metadata = new StringBuilder(files.Length * 80);
        var prefix = Path.GetFullPath(petRoot) + Path.DirectorySeparatorChar;
        long total = 0;
        long maxTicks = 0;
        foreach (var file in files)
        {
            var info = new FileInfo(file);
            total += info.Length;
            maxTicks = Math.Max(maxTicks, info.LastWriteTimeUtc.Ticks);
            var relative = file.StartsWith(prefix, StringComparison.OrdinalIgnoreCase)
                ? file[prefix.Length..]
                : file;
            metadata.Append(relative).Append(':').Append(info.Length).Append(':')
                .Append(info.LastWriteTimeUtc.Ticks).Append('\n');
        }
        var signature = files.Length + ":" + total + ":" + maxTicks + ":"
            + Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(metadata.ToString())))[..16];

        var cachePath = Path.Combine(App.DataDirectory, "asset-cache.json");
        try
        {
            if (File.Exists(cachePath))
            {
                var cached = JsonSerializer.Deserialize<AssetCacheEntry>(File.ReadAllText(cachePath));
                if (cached != null && cached.Signature == signature && cached.Hash.Length == 16)
                {
                    App.WriteLog("ASSET_HASH mode=cached files=" + files.Length);
                    return cached.Hash;
                }
            }
        }
        catch (Exception ex) when (ex is IOException or JsonException or UnauthorizedAccessException or NullReferenceException)
        {
            App.WriteLog("ASSET_HASH cache_reset");
        }

        using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        foreach (var file in files)
            hash.AppendData(File.ReadAllBytes(file));
        var value = Convert.ToHexString(hash.GetHashAndReset())[..16];
        try
        {
            Directory.CreateDirectory(App.DataDirectory);
            File.WriteAllText(cachePath, JsonSerializer.Serialize(new AssetCacheEntry
            {
                Signature = signature,
                Hash = value
            }));
        }
        catch (IOException) { }
        catch (UnauthorizedAccessException) { }
        App.WriteLog("ASSET_HASH mode=full files=" + files.Length);
        return value;
    }
}
