using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Layout;
using Avalonia.Media;
using Avalonia.Media.Imaging;
using Avalonia.Media.Transformation;
using Avalonia.Threading;
using DiyaMeditation.Models;
using DiyaMeditation.Services;
using FlashCap;

namespace DiyaMeditation.Views;

public partial class HomeView : UserControl
{
    private VisitorData? _visitor;
    private bool _busy;
    private bool _pipelineRunning;

    // Camera preview: the UI owns the camera so the feed has zero lag. Every frame
    // is painted to PreviewImage; every Nth is forwarded to the identify process.
    private const int ForwardEveryNthFrame = 3;   // ~10fps to detection at a 30fps camera
    private CaptureDevice? _capture;
    private IdentifySession? _session;
    private volatile bool _frozen;                // stop repainting → last frame stays
    private byte[]? _latestFrame;                 // most recent frame bytes (for display)
    private int _displayScheduled;                // 0/1 guard: coalesce UI-thread posts
    private long _frameCount;
    private Bitmap? _previewBitmap;               // current PreviewImage.Source we own

    public HomeView()
    {
        InitializeComponent();
        Console.WriteLine("[diag] HomeView constructed");
        Loaded += async (_, _) => { Console.WriteLine("[diag] Loaded fired"); await StartIdentifyAsync(); };
    }

    /// <summary>Watch the camera for a face and identify the visitor.</summary>
    private async Task StartIdentifyAsync()
    {
        if (_busy) return;
        // Never identify while a session is running. Doing so re-opens the C920 that
        // the pipeline's own gaze stage (visual_test6.py) needs, re-shows the MATCHED
        // screen mid-session, and fires doomed pipeline spawns that only the
        // run1.sh flock stops.
        if (_pipelineRunning)
        {
            Console.WriteLine("[Diya] identify suppressed — a session is already running");
            return;
        }
        _busy = true;
        IdentifySession? session = null;
        try
        {
            _visitor = null;
            DetailsPanel.IsVisible = false;
            RetryButton.IsVisible = false;
            HideMatched();   // fresh visitor — clear any previous confirmation
            HideMatchBadge();
            IdentifyHint.Text = "Please take a seat.";
            LiveStatus.Foreground = Brush.Parse("#9CA3AF");
            LiveStatus.Text = "Preparing the kiosk — aligning sensors…";
            StatusText.Text = "";
            ResetPreview();

            // Hardware calibration (latest_A: HOME4 → SHOOT3 → trigger_y → CHEST4 →
            // EYE4) runs BEFORE face recognition: the rig homes, deploys, waits for
            // the visitor to sit (LD2410 radar), then aligns the chest and eye
            // cameras to them. It must complete before StartCameraAsync() below,
            // because EYE4 uses the same C920 the identify step streams from.
            var calib = await PipelineRunner.RunCalibrationAsync();
            if (!calib.Completed || calib.ExitCode != 0)
            {
                LiveStatus.Foreground = Brushes.IndianRed;
                LiveStatus.Text = calib.ExitCode == 2
                    ? "Hardware fault detected — operator attention required."
                    : $"Sensor calibration failed{(calib.Error is null ? "" : $": {calib.Error}")}. Tap \"Retry\", or enter your name below.";
                IdentifyHint.Text = "";
                RetryButton.IsVisible = true;
                return;
            }

            IdentifyHint.Text = "Look at the camera to check in.";
            LiveStatus.Foreground = Brush.Parse("#9CA3AF");
            LiveStatus.Text = "Looking for your face…";

            // The UI owns the camera (zero-lag feed); if it can't open, fall back to
            // the manual name entry rather than blocking the identify process forever.
            try
            {
                await StartCameraAsync();
            }
            catch (Exception ex)
            {
                LiveStatus.Foreground = Brushes.IndianRed;
                LiveStatus.Text = $"Camera unavailable: {ex.Message}. Enter your name below.";
                RetryButton.IsVisible = true;
                return;
            }

            // Start the identify process and stream camera frames into it.
            session = IdentifyRunner.Start();
            _session = session;

            var result = await session.Completion;
            Console.WriteLine($"[timing] {DateTime.Now:HH:mm:ss.fff} identify process fully exited");

            // Confirm recognition BEFORE the camera release below. That release is
            // ~200ms and must stay on the critical path (see comment further down),
            // so painting the overlay first means the visitor sees "MATCHED" the
            // moment they are recognised instead of a fifth of a second later.
            if (result.Matched && !string.IsNullOrWhiteSpace(result.Name))
            {
                ShowMatchBadge(matched: true, "Matched");
                // MatchedOverlay is full-screen and paints on top of everything,
                // including this badge — without a beat here, it buries the badge
                // in the same frame it appears in, so the visitor never sees it.
                await Task.Delay(400);
                ShowMatched(result.Name!);
                Console.WriteLine($"[timing] {DateTime.Now:HH:mm:ss.fff} MATCHED overlay shown");
            }
            else
            {
                ShowMatchBadge(matched: false, "Not Matched");
            }

            // Freeze on the matched frame, then FULLY release the camera before the
            // pipeline is spawned. This await must stay on the critical path: FlashCap
            // opens the V4L2 device without O_CLOEXEC, so any process forked while the
            // camera is still open inherits the fd and pins /dev/video0 open for its
            // entire lifetime. run1.sh's children (Front, splitGaze) then fail with
            // "can't open camera by index" and the pipeline hangs forever.
            // Releasing this concurrently to save ~200ms is NOT safe — it deadlocks.
            _frozen = true;
            var swCam = System.Diagnostics.Stopwatch.StartNew();
            await StopCameraAsync();
            Console.WriteLine($"[timing] {DateTime.Now:HH:mm:ss.fff} camera released (took {swCam.ElapsedMilliseconds}ms, before pipeline spawn)");

            if (!result.Matched || string.IsNullOrWhiteSpace(result.Name))
            {
                // Unmatched (or a fatal error) — stay on this screen, do NOT advance.
                LiveStatus.Foreground = Brushes.IndianRed;
                LiveStatus.Text = result.Error is null or "unmatched"
                    ? "Unmatched — we couldn't recognize you. Tap \"Retry\", or enter your name."
                    : $"Couldn't identify you: {result.Error}";
                IdentifyHint.Text = "";
                RetryButton.IsVisible = true;
                return;
            }

            // Verified → show it, then ApplyVisitor starts the session (next step).
            ApplyVisitor(new VisitorData { Name = result.Name!, Email = result.Email ?? "" });
        }
        finally
        {
            _session = null;
            if (session is not null)
                await session.DisposeAsync();
            await StopCameraAsync();   // idempotent
            _busy = false;
        }
    }

    // ── Camera preview (FlashCap; UI-owned for a lag-free feed) ─────────────────

    private async Task StartCameraAsync()
    {
        // FRS must use the Logitech webcam, never one of the other attached cameras
        // (thermal, RealSense depth, Arducam) — those aren't suitable for face
        // recognition and enumeration order isn't guaranteed to put the Logitech
        // one first. Match by name (override via DIYA_CAMERA_NAME), falling back to
        // the first available camera only if no Logitech device is present.
        var nameFilter = Environment.GetEnvironmentVariable("DIYA_CAMERA_NAME") is { Length: > 0 } n ? n : "C920";

        var candidates = new CaptureDevices().EnumerateDescriptors()
            .Where(d => d.Characteristics.Length > 0)
            .ToArray();

        var descriptor = candidates.FirstOrDefault(d => d.Name.Contains(nameFilter, StringComparison.OrdinalIgnoreCase))
            ?? candidates.FirstOrDefault()
            ?? throw new InvalidOperationException("no camera device found");

        // Prefer a JPEG format (small over the pipe); otherwise the smallest frame
        // near 640x480. FlashCap hands us decodable image bytes either way, and both
        // Avalonia (display) and cv2.imdecode (Python) accept JPEG or BMP.
        var characteristics = descriptor.Characteristics
            .OrderByDescending(c => c.PixelFormat == PixelFormats.JPEG)
            .ThenBy(c => Math.Abs(c.Width * c.Height - 640 * 480))
            .First();

        _frameCount = 0;
        _frozen = false;
        _capture = await descriptor.OpenAsync(characteristics, OnFrameAsync);
        await _capture.StartAsync();
    }

    private Task OnFrameAsync(PixelBufferScope bufferScope)
    {
        // Copy out the frame bytes and release the capture buffer promptly.
        var image = bufferScope.Buffer.CopyImage();

        // Forward only every Nth frame to the identify process (non-blocking; the
        // session drops it if a write is still in flight — never lags the preview).
        if (Interlocked.Increment(ref _frameCount) % ForwardEveryNthFrame == 0)
            _session?.SubmitFrame(image);

        // Repaint the preview, coalescing to at most one pending UI-thread post.
        _latestFrame = image;
        if (Interlocked.Exchange(ref _displayScheduled, 1) == 0)
            Dispatcher.UIThread.Post(UpdatePreview);

        return Task.CompletedTask;
    }

    private void UpdatePreview()
    {
        Interlocked.Exchange(ref _displayScheduled, 0);
        if (_frozen) return;

        var bytes = _latestFrame;
        if (bytes is null) return;

        try
        {
            using var ms = new MemoryStream(bytes);
            var bmp = new Bitmap(ms);
            PreviewImage.Source = bmp;
            PreviewPlaceholder.IsVisible = false;
            _previewBitmap?.Dispose();
            _previewBitmap = bmp;
        }
        catch
        {
            // Undecodable frame — skip it, keep the last good one.
        }
    }

    private void ResetPreview()
    {
        _frozen = false;
        _latestFrame = null;
        PreviewImage.Source = null;
        PreviewPlaceholder.IsVisible = true;
        _previewBitmap?.Dispose();
        _previewBitmap = null;
    }

    private async Task StopCameraAsync()
    {
        var cap = _capture;
        _capture = null;
        if (cap is null) return;
        try { await cap.StopAsync(); } catch { /* already stopped */ }
        try { await cap.DisposeAsync(); } catch { /* already gone */ }
    }

    /// <summary>
    /// Full-screen recognition confirmation. Stays up while the pipeline starts —
    /// the meditation video covers it a moment later, so no artificial hold is
    /// needed (and none is added: a timed pause here would be exactly the kind of
    /// dead air the kiosk is meant to avoid).
    /// </summary>
    private void ShowMatched(string name)
    {
        MatchedName.Text = name;
        MatchedSub.Text = "Starting your session…";
        MatchedOverlay.IsVisible = true;
    }

    private void HideMatched() => MatchedOverlay.IsVisible = false;

    /// <summary>
    /// Small badge under the camera preview, distinct from the full-screen
    /// <see cref="ShowMatched"/> overlay: green "Matched" or red "Not Matched",
    /// fading + scaling in via the Transitions declared on MatchBadge in XAML.
    /// </summary>
    private void ShowMatchBadge(bool matched, string label)
    {
        MatchBadge.Background = matched ? Brush.Parse("#16A34A") : Brush.Parse("#DC2626");
        MatchBadgeIcon.Text = matched ? "✓" : "✗";
        MatchBadgeText.Text = label;

        // Start from the "hidden" transform/opacity, then flip to visible on the
        // next render pass so the Transitions above actually animate the change
        // instead of snapping straight to the end state.
        MatchBadge.Opacity = 0;
        MatchBadge.RenderTransform = TransformOperations.Parse("scale(0.7)");
        MatchBadge.IsVisible = true;
        Dispatcher.UIThread.Post(() =>
        {
            MatchBadge.Opacity = 1;
            MatchBadge.RenderTransform = TransformOperations.Parse("scale(1)");
        }, DispatcherPriority.Render);
    }

    private void HideMatchBadge()
    {
        MatchBadge.IsVisible = false;
        MatchBadge.Opacity = 0;
        MatchBadge.RenderTransform = TransformOperations.Parse("scale(0.7)");
    }

    private void ApplyVisitor(VisitorData v)
    {
        _visitor = v;
        NameText.Text = v.Name;
        EmailText.Text = string.IsNullOrWhiteSpace(v.Email) ? "" : $"Email: {v.Email}";
        DetailsPanel.IsVisible = true;
        NameBox.Text = v.Name;

        LiveStatus.Foreground = Brush.Parse("#16A34A");
        LiveStatus.Text = $"✓ Verified — welcome, {v.Name}. Starting your session…";
        IdentifyHint.Text = "";
        RetryButton.IsVisible = false;

        // Successful identification auto-starts the pipeline (no button press).
        _ = StartPipelineAsync();
    }

    private async void OnRetry(object? sender, RoutedEventArgs e)
        => await StartIdentifyAsync();

    /// <summary>
    /// Manual fallback: if the camera didn't recognize anyone, build a visitor from
    /// the typed name and start the same pipeline.
    /// </summary>
    private async void OnStart(object? sender, RoutedEventArgs e)
    {
        if (_visitor is null)
        {
            var typedName = NameBox.Text?.Trim();
            if (string.IsNullOrWhiteSpace(typedName))
            {
                StatusText.Foreground = Brushes.IndianRed;
                StatusText.Text = "Look at the camera, or enter your name.";
                return;
            }

            _visitor = new VisitorData
            {
                Name = typedName,
                Email = EmailBox.Text?.Trim() ?? "",
            };
        }

        await StartPipelineAsync();
    }

    /// <summary>
    /// Runs run1.sh (which drives the cameras/CV and the headless meditation-app),
    /// waits for it to finish, then displays the newest report PDF in-app.
    /// </summary>
    private async Task StartPipelineAsync()
    {
        if (_pipelineRunning) return;
        _pipelineRunning = true;

        StatusText.Foreground = Brush.Parse("#6B7280");
        StatusText.Text = "Please wait — running your session…";
        LiveStatus.Foreground = Brush.Parse("#6B7280");
        LiveStatus.Text = "Session in progress…";

        // The external pipeline (its camera sub-stages: Front, acquisition,
        // morphing, ...) owns the screen while it runs, and each stage is a separate
        // process that opens its own window. Hiding the kiosk here used to expose the
        // desktop and taskbar during every inter-stage gap. Instead stay visible
        // showing a black backdrop: the stage windows draw on top of it, and the gaps
        // read as black rather than as the machine dropping to the desktop.
        var window = TopLevel.GetTopLevel(this) as Window;
        HideMatched();
        HideMatchBadge();
        SessionBackdrop.IsVisible = true;
        if (window is not null && window.WindowState != WindowState.FullScreen)
            window.WindowState = WindowState.FullScreen;

        // Snapshot the newest report BEFORE the session so we can tell a PDF
        // generated by THIS run from a stale one left by a previous visitor.
        // Only a fresh PDF may be renamed after the current visitor — renaming
        // a stale report would stamp their name on someone else's session.
        var pdfBefore = ReportRenderer.FindNewestPdf();
        var pdfBeforeTime = pdfBefore is not null
            ? File.GetLastWriteTimeUtc(pdfBefore)
            : DateTime.MinValue;

        PipelineResult result;
        try
        {
            result = await PipelineRunner.RunAsync();
        }
        finally
        {
            // Do NOT hide SessionBackdrop here: rendering a ~23MB report PDF
            // takes seconds, and dropping the backdrop before ReportOverlay is
            // up exposed the FRS home screen in the gap. The backdrop stays
            // until the report (or its error message) is actually on screen.
            if (window is not null)
            {
                if (!window.IsVisible) window.Show();
                window.WindowState = WindowState.FullScreen;
                window.Activate();
            }
        }

        try
        {
            var pdf = ReportRenderer.FindNewestPdf();

            var isFresh = pdf is not null
                && (pdf != pdfBefore || File.GetLastWriteTimeUtc(pdf) > pdfBeforeTime);
            if (isFresh && !string.IsNullOrWhiteSpace(_visitor?.Name))
                pdf = ReportRenderer.RenameForVisitor(pdf!, _visitor!.Name);

            if (pdf is not null)
            {
                try
                {
                    var pages = await ReportRenderer.RenderPagesAsync(pdf);
                    ShowReport(pages);
                }
                catch (Exception ex)
                {
                    ShowReportMessage($"A report was found but could not be displayed.\n{ex.Message}");
                }
            }
            else
            {
                ShowReportMessage(result.Completed
                    ? $"No report was found in {ReportRenderer.ReportDir}."
                    : $"The session could not start:\n{result.Error}");
            }
        }
        finally
        {
            // ReportOverlay (or its message) is on screen now — safe to drop
            // the black backdrop without exposing the FRS page.
            SessionBackdrop.IsVisible = false;
            _pipelineRunning = false;
        }
    }

    private void ShowReport(List<Bitmap> pages)
    {
        ReportPages.Children.Clear();

        if (pages.Count == 0)
        {
            ShowReportMessage("The report has no pages.");
            return;
        }

        foreach (var bmp in pages)
        {
            var img = new Image { Source = bmp, Stretch = Stretch.Uniform, MaxWidth = 900 };
            ReportPages.Children.Add(new Border
            {
                Background = Brushes.White,
                CornerRadius = new CornerRadius(4),
                HorizontalAlignment = HorizontalAlignment.Center,
                Child = img,
            });
        }

        ReportMessage.IsVisible = false;
        ReportScroll.IsVisible = true;
        ReportOverlay.IsVisible = true;
    }

    private void ShowReportMessage(string message)
    {
        ReportPages.Children.Clear();
        ReportScroll.IsVisible = false;
        ReportMessage.Text = message;
        ReportMessage.IsVisible = true;
        ReportOverlay.IsVisible = true;
    }

    /// <summary>Return button: reset everything for the next visitor.</summary>
    private async void OnReturn(object? sender, RoutedEventArgs e)
    {
        ReportOverlay.IsVisible = false;
        ReportPages.Children.Clear();
        await StartIdentifyAsync();
    }
}
