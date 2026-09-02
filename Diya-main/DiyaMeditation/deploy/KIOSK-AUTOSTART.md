# Kiosk autostart & automatic login

How to make a machine boot straight into the Diya Meditation kiosk. Verified on
Ubuntu 24.04, GNOME on Wayland, GDM.

## 1. Install the app

```sh
sudo dpkg -i package/diya-meditation_1.5.0_amd64.deb
```

Installs to `/opt/diya-meditation/DiyaMeditation`. Confirm before going further —
if the binary is missing, autostart runs and silently does nothing:

```sh
ls -l /opt/diya-meditation/DiyaMeditation
```

## 2. Autostart at login

```sh
./setup-autostart.sh              # autostart only
./setup-autostart.sh --autologin  # also enable GDM automatic login
```

This installs `diya-meditation-start.sh` to `~/.local/bin` and writes
`~/.config/autostart/diya-meditation.desktop` pointing at it.

### Why a wrapper script

The Desktop Entry spec forbids `;`, `>`, `&` and quote characters in `Exec=`.
Putting the delay, environment variable and log redirect directly in the
`.desktop` file makes it fail `desktop-file-validate` and it may not run at all.
The wrapper keeps `Exec=` a plain path.

### What the wrapper does

| Step | Why |
|---|---|
| `sleep 4` | Waits for the Wayland session. Launching too early fails silently. |
| `DIYA_API_BASE` | Registration API the kiosk fetches scanned passes from. |
| `> /tmp/diya.log 2>&1` | Captures the reason for any failure. |

Override with `DIYA_START_DELAY`, `DIYA_API_BASE`, or `DIYA_LOG`.

## 3. Alternative: systemd user service

The `.deb` ships `diya-meditation.service`, which adds `Restart=always` so the
app relaunches if it crashes — better for an unattended kiosk:

```sh
systemctl --user enable --now diya-meditation
```

**Use one or the other.** Enabling the service *and* the autostart entry
launches the app twice.

## 4. Lock down the desktop

`setup-kiosk.sh` disables the GNOME keybindings that would let a visitor escape
the app (close window, switch apps, run dialog).

## Troubleshooting

```sh
cat /tmp/diya.log
```

The app logs `[Diya] v1.5.0 OnOpened — applying fullscreen (kiosk=...)` on
startup, which confirms whether kiosk mode engaged.

**On Wayland**, a client cannot force itself above the compositor the way it can
on X11, so the GNOME top bar may remain visible even in fullscreen. If that
happens, a dedicated GNOME kiosk session is more reliable than app-side window
flags.

To undo automatic login, restore the backup:

```sh
sudo cp /etc/gdm3/custom.conf.bak /etc/gdm3/custom.conf
```
