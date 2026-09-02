using System;
using Avalonia.Controls;
using Avalonia.Input;
using Avalonia.Threading;

namespace DiyaMeditation.Views;

public partial class MainWindow : Window
{
    public MainWindow()
    {
        InitializeComponent();
    }

    /// <summary>
    /// Kiosk lockdown: no decorations, no taskbar, cannot be closed or minimised —
    /// the machine is unattended and self-service, like an ATM. Set DIYA_KIOSK=0 to
    /// disable for maintenance (otherwise the box needs a TTY to get out of).
    /// </summary>
    private static bool KioskMode =>
        Environment.GetEnvironmentVariable("DIYA_KIOSK") != "0";

    protected override void OnOpened(EventArgs e)
    {
        base.OnOpened(e);
        Console.WriteLine($"[Diya] v1.5.0 OnOpened — applying fullscreen (kiosk={KioskMode})");
        GoFullScreen();

        // Wayland/GNOME maps the window in a normal state first, so re-assert
        // fullscreen right after opening. In kiosk mode the check keeps running for
        // the life of the app: a stage window closing, or the WM restoring focus,
        // can drop the shell out of fullscreen and expose the desktop underneath.
        var attempts = 0;
        var timer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(250) };
        timer.Tick += (_, _) =>
        {
            GoFullScreen();
            if (++attempts >= 6 && !KioskMode)
                timer.Stop();
            else if (attempts >= 6)
                timer.Interval = TimeSpan.FromSeconds(2);   // steady-state watchdog
        };
        timer.Start();
    }

    /// <summary>
    /// Hidden exit key. There is no visible close control anywhere in the kiosk, so
    /// "q" is the operator's way out — matching mpv/ffplay/OpenCV, which all quit on
    /// "q" too, so the same key works whichever stage currently owns the screen.
    /// </summary>
    protected override void OnKeyDown(KeyEventArgs e)
    {
        if (e.Key == Key.Q)
        {
            Console.WriteLine("[Diya] 'q' pressed — exiting kiosk");
            _quitRequested = true;
            e.Handled = true;
            Close();
            return;
        }
        base.OnKeyDown(e);
    }

    private bool _quitRequested;

    /// <summary>Swallow Alt+F4 / WM close so a visitor cannot exit to the desktop.</summary>
    protected override void OnClosing(WindowClosingEventArgs e)
    {
        // "q" is the one sanctioned way out; every other close request (Alt+F4, WM
        // close, a stray click on a decoration if one ever appears) is refused.
        if (KioskMode && !_quitRequested)
        {
            Console.WriteLine("[Diya] close request ignored (kiosk mode — press 'q' to exit)");
            e.Cancel = true;
            GoFullScreen();
            return;
        }
        base.OnClosing(e);
    }

    private void GoFullScreen()
    {
        if (WindowState != WindowState.FullScreen)
            WindowState = WindowState.FullScreen;
        Console.WriteLine($"[Diya] fullscreen check -> WindowState={WindowState}, ClientSize={ClientSize}");
    }
}
