using Avalonia;
using System;
using System.IO;

namespace DiyaMeditation;

internal static class Program
{
    // Held for the lifetime of the process; releasing it frees the single-instance
    // lock. Static so the GC cannot collect it while the app is running.
    private static FileStream? _instanceLock;

    // Initialization code. Don't use any Avalonia, third-party APIs or any
    // SynchronizationContext-reliant code before AppMain is called: things aren't
    // initialized yet and stuff might break.
    [STAThread]
    public static void Main(string[] args)
    {
        if (!TryAcquireInstanceLock())
        {
            // A second kiosk would run its own pipeline against the same cameras,
            // which is how overlapping stage windows (two meditation players, two
            // Front windows) end up on screen at once.
            Console.Error.WriteLine(
                "[Diya] another instance is already running — exiting. " +
                "Stop it first, or set DIYA_LOCK_FILE to run a second one deliberately.");
            return;
        }

        BuildAvaloniaApp().StartWithClassicDesktopLifetime(args);
    }

    /// <summary>
    /// Exclusive lock on a well-known file. The OS drops it automatically if the
    /// process is killed, so a crashed kiosk never leaves a stale lock behind.
    /// </summary>
    private static bool TryAcquireInstanceLock()
    {
        var path = Environment.GetEnvironmentVariable("DIYA_LOCK_FILE") is { Length: > 0 } p
            ? p
            : Path.Combine(Path.GetTempPath(), "diya-meditation.lock");
        try
        {
            _instanceLock = new FileStream(
                path, FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);
            return true;
        }
        catch (IOException)
        {
            return false;   // held by another instance
        }
    }

    // Avalonia configuration, don't remove; also used by the visual designer.
    public static AppBuilder BuildAvaloniaApp()
        => AppBuilder.Configure<App>()
            .UsePlatformDetect()
            .WithInterFont()
            .LogToTrace();
}
