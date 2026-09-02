using System;
using System.Buffers.Binary;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Channels;
using System.Threading.Tasks;

namespace DiyaMeditation.Services;

public sealed record IdentifyResult(bool Matched, string? Name, string? Email, double? Confidence, double? Distance, string? Error);

/// <summary>
/// Runs the bundled face-identify client (vendored am-mock-client's client.py, via
/// its --kiosk-identify mode) and WAITS for it to identify a visitor. Detection +
/// embedding happen in that Python process; it calls the identify backend
/// (am-mock-server / am-master-server) — only the resulting vector crosses the
/// network, never a camera frame or photo.
///
/// The camera is owned by the C# UI (so the live preview has zero lag): the UI
/// captures frames and pushes them to the Python process's stdin via
/// <see cref="IdentifySession.SubmitFrame"/>; client.py runs with --frames-stdin and
/// reads them instead of opening a camera itself. The Python process prints one JSON
/// line to stdout when it matches; that is parsed into <see cref="IdentifyResult"/>.
///
/// There is intentionally NO timeout: client.py retries its own server health-check
/// and keeps consuming frames until a visitor is identified, mirroring PipelineRunner's
/// "no timeout, script owns its own retry logic".
///
/// Configurable via env vars:
///   DIYA_IDENTIFY_SCRIPT      - full path to client.py (default: &lt;app&gt;/vendor/am-mock-client/client.py)
///   DIYA_IDENTIFY_PYTHON      - python executable (default: python3)
///   DIYA_IDENTIFY_SERVER_URL  - identify backend base URL (passed through to the script)
/// </summary>
public static class IdentifyRunner
{
    private static string PythonExe =>
        Environment.GetEnvironmentVariable("DIYA_IDENTIFY_PYTHON") is { Length: > 0 } p ? p : "python3";

    public static string ScriptPath()
    {
        var custom = Environment.GetEnvironmentVariable("DIYA_IDENTIFY_SCRIPT");
        if (!string.IsNullOrWhiteSpace(custom))
            return custom;
        return Path.Combine(AppContext.BaseDirectory, "vendor", "am-mock-client", "client.py");
    }

    /// <summary>
    /// Starts the identify process and returns a live session. The caller pushes camera
    /// frames via <see cref="IdentifySession.SubmitFrame"/> and awaits
    /// <see cref="IdentifySession.Completion"/> for the result. Dispose the session to
    /// stop the process (e.g. on cancel/navigation).
    /// </summary>
    public static IdentifySession Start(CancellationToken ct = default)
        => new IdentifySession(ScriptPath(), PythonExe, ct);

    internal static IdentifyResult ParseLastJsonLine(string stdout)
    {
        if (string.IsNullOrWhiteSpace(stdout))
            return new IdentifyResult(false, null, null, null, null, "identify client produced no output.");

        var lastLine = stdout.Split('\n', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)[^1];

        try
        {
            using var doc = JsonDocument.Parse(lastLine);
            var root = doc.RootElement;
            var matched = root.TryGetProperty("matched", out var m) && m.GetBoolean();

            if (!matched)
            {
                var err = root.TryGetProperty("error", out var e) ? e.GetString() : "identify client reported no match.";
                return new IdentifyResult(false, null, null, null, null, err);
            }

            var name = root.TryGetProperty("name", out var n) ? n.GetString() : null;
            var email = root.TryGetProperty("email", out var em) ? em.GetString() : null;
            double? confidence = root.TryGetProperty("confidence", out var c) && c.ValueKind == JsonValueKind.Number ? c.GetDouble() : null;
            double? distance = root.TryGetProperty("distance", out var d) && d.ValueKind == JsonValueKind.Number ? d.GetDouble() : null;

            return new IdentifyResult(true, name, email, confidence, distance, null);
        }
        catch (JsonException)
        {
            return new IdentifyResult(false, null, null, null, null, $"Could not parse identify output: {lastLine}");
        }
    }
}

/// <summary>
/// A running face-identify process. Feed it JPEG-encoded camera frames with
/// <see cref="SubmitFrame"/> (non-blocking; stale frames are dropped if the pipe is
/// busy so the UI's capture loop never stalls) and await <see cref="Completion"/> for
/// the <see cref="IdentifyResult"/>.
/// </summary>
public sealed class IdentifySession : IAsyncDisposable
{
    // Consecutive unrecognized-face detections before the identify process reports
    // "unmatched" instead of watching forever. At ~10 forwarded frames/sec that's
    // roughly 4–5 seconds of a face the backend doesn't recognize.
    private const int MaxUnmatchedDetections = 45;

    // Capacity-1, drop-oldest: only the freshest frame is ever queued, so a slow
    // detection pass can never build a backlog or lag the live preview.
    private readonly Channel<byte[]> _frames = Channel.CreateBounded<byte[]>(
        new BoundedChannelOptions(1) { FullMode = BoundedChannelFullMode.DropOldest, SingleReader = true });

    private readonly Process? _proc;
    private readonly Task<IdentifyResult> _completion;
    private readonly CancellationTokenSource _cts;

    public Task<IdentifyResult> Completion => _completion;

    internal IdentifySession(string script, string pythonExe, CancellationToken ct)
    {
        _cts = CancellationTokenSource.CreateLinkedTokenSource(ct);

        if (!File.Exists(script))
        {
            _completion = Task.FromResult(new IdentifyResult(false, null, null, null, null, $"Identify script not found at {script}"));
            _frames.Writer.TryComplete();
            return;
        }

        var psi = new ProcessStartInfo
        {
            FileName = pythonExe,
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
            CreateNoWindow = true,
            WorkingDirectory = Path.GetDirectoryName(script) ?? AppContext.BaseDirectory,
        };
        psi.ArgumentList.Add(script);
        psi.ArgumentList.Add("--kiosk-identify");
        psi.ArgumentList.Add("--frames-stdin");
        // Give up (report "unmatched") after a face is seen but not recognized for
        // this many consecutive detections (~a few seconds at the forwarded rate),
        // so an unenrolled visitor gets a clear result instead of an endless wait.
        psi.ArgumentList.Add("--max-unmatched");
        psi.ArgumentList.Add(MaxUnmatchedDetections.ToString());

        var serverUrl = Environment.GetEnvironmentVariable("DIYA_IDENTIFY_SERVER_URL");
        if (!string.IsNullOrWhiteSpace(serverUrl))
            psi.Environment["DIYA_IDENTIFY_SERVER_URL"] = serverUrl;

        try
        {
            _proc = new Process { StartInfo = psi };
            _completion = RunAsync(_proc);
        }
        catch (Exception ex)
        {
            // python3 missing, permission denied, etc.
            _completion = Task.FromResult(new IdentifyResult(false, null, null, null, null, ex.Message));
            _frames.Writer.TryComplete();
        }
    }

    /// <summary>
    /// Queue a JPEG-encoded frame to forward to the identify process. Non-blocking; if a
    /// previous frame hasn't been written yet it is dropped in favour of this newer one.
    /// </summary>
    public void SubmitFrame(byte[] jpeg) => _frames.Writer.TryWrite(jpeg);

    private async Task<IdentifyResult> RunAsync(Process proc)
    {
        var stdout = new StringBuilder();
        void CaptureOut(string? data)
        {
            if (data is null) return;
            lock (stdout) stdout.AppendLine(data);
            Console.WriteLine($"[timing] {DateTime.Now:HH:mm:ss.fff} result JSON received on stdout");
        }
        void CaptureErr(string? data)
        {
            if (data is null) return;
            Console.WriteLine($"[identify] {data}");
            if (data.Contains("Matched:"))
                Console.WriteLine($"[timing] {DateTime.Now:HH:mm:ss.fff} match known (now waiting for python to exit)");
        }

        try
        {
            proc.OutputDataReceived += (_, e) => CaptureOut(e.Data);
            proc.ErrorDataReceived += (_, e) => CaptureErr(e.Data);

            if (!proc.Start())
                return new IdentifyResult(false, null, null, null, null, "Failed to start the identify process.");

            proc.BeginOutputReadLine();
            proc.BeginErrorReadLine();

            // Pump frames into the child's stdin on a background task; it ends when the
            // channel completes (Dispose) or the child exits (broken pipe, swallowed).
            var pump = PumpFramesAsync(proc.StandardInput.BaseStream, _cts.Token);

            await proc.WaitForExitAsync(_cts.Token);

            _frames.Writer.TryComplete();
            try { await pump; } catch { /* pump errors are non-fatal */ }

            string text;
            lock (stdout) text = stdout.ToString().Trim();
            return IdentifyRunner.ParseLastJsonLine(text);
        }
        catch (Exception ex)
        {
            // cancelled, killed, etc.
            return new IdentifyResult(false, null, null, null, null, ex.Message);
        }
    }

    private async Task PumpFramesAsync(Stream stdin, CancellationToken ct)
    {
        var header = new byte[4];
        try
        {
            await foreach (var jpeg in _frames.Reader.ReadAllAsync(ct))
            {
                BinaryPrimitives.WriteUInt32BigEndian(header, (uint)jpeg.Length);
                await stdin.WriteAsync(header, ct);
                await stdin.WriteAsync(jpeg, ct);
                await stdin.FlushAsync(ct);
            }
            // Zero-length terminator tells client.py the stream ended cleanly.
            BinaryPrimitives.WriteUInt32BigEndian(header, 0);
            await stdin.WriteAsync(header, ct);
            await stdin.FlushAsync(ct);
        }
        catch (Exception)
        {
            // The child closes stdin the moment it matches and exits, so a write here
            // races into a broken pipe / cancellation — expected, nothing to do.
        }
    }

    public async ValueTask DisposeAsync()
    {
        _frames.Writer.TryComplete();
        try { _cts.Cancel(); } catch { /* ignore */ }

        if (_proc is not null)
        {
            try
            {
                if (!_proc.HasExited)
                {
                    _proc.Kill(entireProcessTree: true);
                    await _proc.WaitForExitAsync();
                }
            }
            catch { /* already gone */ }
            _proc.Dispose();
        }

        _cts.Dispose();
    }
}
