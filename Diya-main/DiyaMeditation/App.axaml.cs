using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Markup.Xaml;
using DiyaMeditation.Views;

namespace DiyaMeditation;

public partial class App : Application
{
    public override void Initialize()
    {
        AvaloniaXamlLoader.Load(this);
    }

    public override void OnFrameworkInitializationCompleted()
    {
        if (ApplicationLifetime is IClassicDesktopStyleApplicationLifetime desktop)
        {
            // The kiosk shell window is the single, locked-down top-level window.
            desktop.MainWindow = new MainWindow();

            // Prevent the app from shutting down if the main window is somehow closed;
            // we control shutdown explicitly via the secret exit shortcut.
            desktop.ShutdownMode = ShutdownMode.OnExplicitShutdown;
        }

        base.OnFrameworkInitializationCompleted();
    }
}
