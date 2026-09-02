# Diya Meditation — Setup & Commands

All the commands for installing, running, and auto-starting the kiosk on Ubuntu.
**Latest version: 1.5.0**

> Pick the package matching your machine's architecture
> (check with `dpkg --print-architecture`):
> - `amd64` -> normal x86 PCs
> - `arm64` -> Apple Silicon VMs / ARM devices

---

## Which should I use? (.deb vs Docker)

- **`.deb` install (Section 1)** — the **real kiosk deployment**. Use this on the
  actual museum/Ubuntu machine. Gives true fullscreen, auto-start on boot,
  auto-restart on crash, and GNOME lockdown.
- **Docker (Section 11)** — **UI preview only**, viewed in a browser via noVNC.
  Handy for a quick look without installing anything system-wide. NOT a real
  kiosk: no boot autostart, no lockdown, no crash-restart.

**On a real Ubuntu machine, use the `.deb`.**

> **Online registration (v1.5.0+):** the kiosk shows a **QR code on screen**. The
> visitor scans it with their **phone**, fills in the registration form on their
> phone, and the kiosk **advances automatically** once they submit. No QR scanner
> or camera is needed at the kiosk — but the kiosk **must have internet** and know
> the API URL (see Sections 4 and 5). A name-entry fallback is also on screen.

---

## 1. Install on Ubuntu

### a) Download from GitHub and install
```bash
cd ~
rm -f diya-meditation_1.5.0_amd64.deb
wget https://github.com/AyushIsOn/Diya/raw/main/package/diya-meditation_1.5.0_amd64.deb
sudo dpkg -i ./diya-meditation_1.5.0_amd64.deb
```

If it ever complains about a missing dependency:
```bash
sudo apt -f install
```

### b) Already have the .deb file? (offline / no GitHub)
If the `.deb` is already on the machine (USB stick, shared folder, scp, etc.),
skip the download and install the local file directly — the package itself is
self-contained (bundles the .NET runtime):

```bash
sudo dpkg -i ./diya-meditation_1.5.0_amd64.deb
sudo apt -f install     # only if it reports a missing dependency
```

Ways to get the file onto the machine without GitHub:
- **USB drive** — copy the `.deb` over and plug it in
- **VM shared folder** — drop it in the shared folder from the host
- **scp** — `scp diya-meditation_1.5.0_amd64.deb user@machine:~/`

### c) Update to a newer build (reinstall)
When a new `.deb` is published (e.g. a new feature like the visitor photo), you
must **stop the running app first** — otherwise `dpkg -i` replaces the files on
disk but the old app keeps running until it restarts.

```bash
# 1. Stop the running app
systemctl --user stop diya-meditation 2>/dev/null   # if you use the service
pkill -f DiyaMeditation                             # kill any running instance

# 2. Re-download the latest package (remove the stale copy first)
cd ~
rm -f diya-meditation_1.5.0_amd64.deb
wget https://github.com/AyushIsOn/Diya/raw/main/package/diya-meditation_1.5.0_amd64.deb

# 3. Reinstall
sudo dpkg -i ./diya-meditation_1.5.0_amd64.deb
sudo apt -f install     # only if it reports a missing dependency

# 4. Start it again (or reboot)
diya-meditation
# or: systemctl --user start diya-meditation
```

> Use the `arm64` filename on ARM devices. If unsure of the arch, run
> `dpkg --print-architecture`.

## 2. Run it

```bash
diya-meditation
```

...or launch **"Diya Meditation"** from the app menu (press Super, search for it).
It opens **fullscreen**.

## 3. Exit / minimise the kiosk

The app behaves like a normal window now:
- **Close** it with `Alt + F4` (or a window-manager close).
- **Minimise** it like any app — it appears in the taskbar/dock, so you can bring
  it back.

It still opens **fullscreen**, but is no longer top-most, so the taskbar and other
windows are reachable.

> The old `Ctrl + Shift + Alt + Q` exit shortcut has been **removed**.

---

## 4. Point the kiosk at the registration API (`DIYA_API_BASE`)

When a visitor scans their QR pass, the kiosk reads the short id and fetches their
details from the registration API. Tell the kiosk where that API lives with the
`DIYA_API_BASE` environment variable.

- Default (baked into the build): `https://diya-registration.onrender.com`
- Change it to **your** deployed URL (from Section 5) in whichever way matches how
  you start the app:

**If you auto-start via the systemd service** (`/usr/lib/systemd/user/diya-meditation.service`),
it already contains a line you can edit:
```ini
Environment=DIYA_API_BASE=https://YOUR-SERVICE.onrender.com
```
Then:
```bash
systemctl --user daemon-reload
systemctl --user restart diya-meditation
```

**If you launch it from the autostart `.desktop`** (Section 6), the `Exec` line
exports it (see that section).

**If you run it by hand:**
```bash
DIYA_API_BASE=https://YOUR-SERVICE.onrender.com diya-meditation
```

> Quick check the kiosk can reach the API:
> ```bash
> curl https://YOUR-SERVICE.onrender.com/api/health   # expect {"ok":true}
> ```

---

## 5. Deploy the registration website + API (Render, free)

The `server/` folder is a small Node/Express API that also serves the
registration website (`registration/index.html`). It stores visitors in Postgres.

### a) Pick a database
- **Render Postgres** (one click via `render.yaml`) — easiest, but the **free**
  Render database is **deleted after 30 days**.
- **Neon / Supabase** free Postgres — persistent; recommended for anything lasting.

### b) Deploy on Render
1. Push this repo to GitHub.
2. Render Dashboard -> **New -> Blueprint** -> select this repo.
   Render reads `render.yaml` and creates the web service (root dir `server/`).
   - Using Render Postgres: the blueprint also creates the DB and wires
     `DATABASE_URL` automatically.
   - Using Neon/Supabase: in the service's **Environment**, set `DATABASE_URL`
     to your connection string (and you can delete the `databases:` block).
3. After it deploys, note the URL, e.g. `https://diya-registration.onrender.com`.
   - Registration website: open that URL in a browser.
   - Health check: `GET /api/health` -> `{"ok":true}`.
4. Put that URL into the kiosk via `DIYA_API_BASE` (Section 4).
5. **For the admin roster feature (Section 5A):** in the service's
   **Environment** tab, add **`ADMIN_KEY`** = a long random secret. Without it the
   admin page is disabled (returns `503 admin disabled`). Changing an env var
   triggers a redeploy — wait for **Live** before using it.

> Free Render web services sleep after ~15 min idle; the first request then
> cold-starts in ~30–50s. The kiosk's lookup timeout accounts for this.

> **Auto-deploy:** make sure the service's **Auto-Deploy** is **On** and the
> **Branch** is `main`, otherwise merging changes to GitHub won't update the live
> site. To force a deploy: **Manual Deploy -> Deploy latest commit**.

### c) Run the server locally (optional, for testing)
```bash
cd server
cp .env.example .env        # then edit DATABASE_URL (use PGSSL=disable for local PG)
npm install
npm start                   # serves site + API on http://localhost:3000
```

---

## 5A. Admin roster upload + phone login (pre-registered people)

An alternative to visitors registering themselves: an **admin pre-loads people
from an Excel sheet**, and each person gets a personal login link. The person opens
their link on their phone, taps a button to open the camera, and **scans the QR on
the kiosk screen** to log in. Their details (and photo) then appear on the kiosk.

> This runs on the **same** Render service as the registration site — no separate
> deploy. It just needs `ADMIN_KEY` set (Section 5, step 5).

### a) Prepare the Excel sheet (.xlsx)
One row per person. Column headers are matched loosely (case-insensitive,
substring), so `Image`, `Image URL`, or `Image Link (Gdrive - ...)` all work.
Only **Name** is required per row. Recognised columns:

| Column (any header containing…) | Stored as |
|---|---|
| `Name` | name (required) |
| `Role` / `Designation` | role |
| `Aadhar` / `Aadhaar` | aadhaar (kept private) |
| `Email` / `Email Id` | email |
| `Image` / `Photo` / `Picture` / `Image Link` | photo URL |

**The image column must be a _direct image URL as plain text_** — a link that
returns the raw image file, e.g. `https://i.ibb.co/xxxx/name.jpg`:
- ✅ Ends in `.jpg` / `.png` / `.webp`, opens as *just the photo* in a browser, public.
- ✅ Type/paste the URL **as text** into the cell (the cell shows the link text).
- ❌ A share/preview **page** link (e.g. `https://ibb.co/...`, Google Drive
  `.../view`), a link needing login, an **inserted picture**, or an
  `=IMAGE("...")` **function** — none of these work (only the cell's text is read).
- ❌ **HEIC** (default iPhone format) can't be decoded — convert to JPG first.

### b) Upload the roster
1. Open **`https://YOUR-SERVICE.onrender.com/admin`**.
2. Enter the **admin key** (the `ADMIN_KEY` value you set on Render).
3. Choose the `.xlsx` file. A preview appears (Aadhaar is masked). **Check the
   preview's Image column shows your URLs** — if it's blank there, the cell isn't
   plain text (see the ❌ cases above).
4. Click **Generate login links**. You get one link per person, of the form
   `https://YOUR-SERVICE.onrender.com/p/<token>`. Copy them (per-row, **Copy all**,
   or **Download as CSV**) and share each person their own link.

> Re-uploading generates **new** links (new people rows). If you fix a sheet and
> re-upload, distribute the newly generated links — the old ones point to the
> earlier rows.

### c) How a person logs in
1. They open their `/p/<token>` link on their **phone** (needs **HTTPS** — Render
   provides it — because the browser only allows the camera on secure pages).
2. It greets them by name; they tap **Proceed to login**, which opens the camera.
3. They point it at the **QR code on the kiosk screen**.
4. The kiosk advances automatically and shows their name (and photo, if the kiosk
   app is up to date — see note below).

### d) Showing the photo on the kiosk
The photo (from the image column) is displayed on the kiosk **only if the kiosk
app includes the photo feature**. If you installed an older `.deb`, everything still
works but no photo shows. To enable it, **rebuild and reinstall the `.deb`**
(Section 10) — or download the prebuilt package from `package/` — so the kiosk has
the latest app; the kiosk needs internet to fetch the photos (it already does for
the API).

> **Privacy note:** the roster holds names, Aadhaar, and photo links. Aadhaar is
> never exposed by the public link (only name/role/photo are). Still, host photos
> somewhere access-appropriate — public image hosts make the photo viewable by
> anyone with the URL; a private bucket is safer for real ID photos.

---

## 6. Auto-start on boot

### a) Create the autostart entry (with a startup delay + API URL + log)
The `sleep 4` waits for the Wayland desktop session to be ready (otherwise the app
can launch too early and fail silently). `DIYA_API_BASE` points it at your API.
The log helps diagnose any failure.

```bash
mkdir -p ~/.config/autostart
cat > ~/.config/autostart/diya-meditation.desktop <<'EOF'
[Desktop Entry]
Type=Application
Name=Diya Meditation
Exec=sh -c 'sleep 4; DIYA_API_BASE=https://YOUR-SERVICE.onrender.com /opt/diya-meditation/DiyaMeditation > /tmp/diya.log 2>&1'
X-GNOME-Autostart-enabled=true
Terminal=false
EOF
```

### b) Enable automatic login (so it boots straight in, no password prompt)
Easiest: **Settings -> System -> Users -> Automatic Login -> ON**

Or via terminal:
```bash
sudo tee /etc/gdm3/custom.conf > /dev/null <<EOF
[daemon]
AutomaticLoginEnable=true
AutomaticLogin=$USER
EOF
```

### c) Reboot to test
```bash
reboot
```

---

## 7. Troubleshooting auto-start

If the app does not appear after reboot, run this and read the output:

```bash
echo "--- did it start? ---"; pgrep -fa DiyaMeditation || echo "NOT running"
echo "--- startup log ---"; cat /tmp/diya.log 2>/dev/null || echo "no log file"
echo "--- autostart entry ---"; cat ~/.config/autostart/diya-meditation.desktop
echo "--- autologin config ---"; grep -iA3 daemon /etc/gdm3/custom.conf 2>/dev/null
echo "--- binary present? ---"; ls -l /opt/diya-meditation/DiyaMeditation
```

What it tells you:
- **NOT running + a log error** -> the app crashed on launch; the log shows why.
- **NOT running + no log** -> the autostart entry never fired (check auto-login actually boots to the desktop without a password prompt).
- **binary missing** -> the v1.5.0 install did not complete; reinstall with `sudo dpkg -i ./diya-meditation_1.5.0_amd64.deb`.
- **scans say "Couldn't reach the server"** -> the kiosk has no internet or
  `DIYA_API_BASE` is wrong (Section 4); test with the `curl .../api/health` check.

---

## 8. General checks

```bash
# What's my session type? (wayland or x11)
echo $XDG_SESSION_TYPE

# What's my CPU architecture? (amd64 or arm64)
dpkg --print-architecture

# Run from terminal to see startup logs (look for "[Diya] ..." lines)
diya-meditation
```

## 9. Uninstall

```bash
sudo apt remove diya-meditation
rm -f ~/.config/autostart/diya-meditation.desktop
```

---

## 10. Build the .deb from source (optional)

### a) Install the .NET 8 SDK on Ubuntu (one time)
```bash
sudo apt update
sudo apt install -y dotnet-sdk-8.0
dotnet --version        # should print 8.0.x
```

> If `dotnet-sdk-8.0` is not found in the default repos on your Ubuntu version,
> add Microsoft's feed first:
> ```bash
> sudo apt install -y wget
> wget https://packages.microsoft.com/config/ubuntu/$(lsb_release -rs)/packages-microsoft-prod.deb -O /tmp/ms.deb
> sudo dpkg -i /tmp/ms.deb
> sudo apt update
> sudo apt install -y dotnet-sdk-8.0
> ```

### b) Build the package
```bash
cd DiyaMeditation
./deploy/build-deb.sh 1.5.0 amd64     # x86 PCs
./deploy/build-deb.sh 1.5.0 arm64     # ARM devices / Apple Silicon VMs
# output: build/diya-meditation_1.5.0_<arch>.deb
```

> Note: `build-deb.sh` wipes the `build/` directory at the start of every run,
> so if you build both architectures, copy the first `.deb` out before building
> the second (otherwise the first one gets deleted).

### c) Run directly from source (no packaging)
```bash
cd DiyaMeditation
dotnet run            # builds + launches fullscreen
```

### d) Edit the pipeline script (run1.sh) & repackage

On successful login the kiosk **automatically** runs a bundled bash pipeline,
**waits for it to finish**, then displays the newest report PDF found in
`/opt/meditation-app/data`. There is no calibration button and no in-between
screen — login goes straight through to the report, with a **Return** button to
reset for the next person.

The pipeline script lives in the source at:

```
DiyaMeditation/scripts/run1.sh    # runs HOME1/SHOOT1/CHEST1/EYE1 .py + meditation-app
```

and is bundled into the package at **`/opt/diya-meditation/scripts/run1.sh`**. To
change the pipeline, edit it in the **unpacked (source) copy** and repackage:

1. Edit `DiyaMeditation/scripts/run1.sh` (this is the file the kiosk runs).
2. Rebuild the package — that's the whole "repackage" step:
   ```bash
   cd DiyaMeditation
   ./deploy/build-deb.sh 1.5.0 amd64      # or arm64
   ```
3. Reinstall on the kiosk (see Section 1c — remember to stop the running app first).

What the kiosk expects on the target machine (the other team provides these):
- **python3.10** installed (`run1.sh` calls `python3.10` explicitly).
- The camera/CV scripts at **`~/Desktop/mark1/`**: `HOME1.py`, `SHOOT1.py`,
  `CHEST1.py`, `EYE1.py` (this path is set by `WORK_DIR` inside `run1.sh`).
- The **`meditation-app`** package installed and on `PATH` — it runs headless and
  writes the report PDF to `/opt/meditation-app/data`.

**Report directory permissions.** `meditation-app` must be able to **write** the
PDF there and the kiosk must **read** it. Both run as the same kiosk user, so hand
that user the folder once (this is included in `deploy/setup-kiosk.sh`):
```bash
sudo mkdir -p /opt/meditation-app/data
sudo chown -R "$USER:$USER" /opt/meditation-app
```

Override paths without rebuilding, via env vars:
- `DIYA_PIPELINE_SCRIPT=/path/to/run1.sh` — the script to run on login
- `DIYA_BASH=/usr/bin/bash` — the shell used to run it
- `DIYA_REPORT_DIR=/some/other/dir` — where to look for the newest PDF

Notes:
- `run1.sh` has **no timeout** — it owns its own retry logic and blocks until the
  pipeline (including `meditation-app`) finishes; only then is the PDF shown.
- If no PDF is found when the pipeline ends, the report screen shows a short
  message instead (still with the Return button).

---

## 11. Run with Docker (browser preview — dev only)

This runs the app on a virtual display (Xvfb) exposed through noVNC, so you can
view it in a web browser. This is for **previewing the UI only** — it is NOT the
real kiosk deployment (use the `.deb` for that).

### a) Install Docker Engine on Ubuntu (one time)
```bash
# Quick install via Docker's convenience script
curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
sudo sh /tmp/get-docker.sh

# Allow running docker without sudo (log out / back in after this)
sudo usermod -aG docker "$USER"
newgrp docker            # apply the group in the current shell

docker --version         # verify
```

### b) Build the image
```bash
cd DiyaMeditation
docker build -t diya-preview -f docker/Dockerfile .
```

### c) Run the container
```bash
docker run --rm -p 8080:8080 diya-preview
```

### d) View it
Open in a browser on the same machine:

```
http://localhost:8080/vnc.html
```

Click **Connect**. Exit the app inside the view with **`Ctrl + Shift + Alt + Q`**.

To stop the container: press `Ctrl + C` in the terminal running it (the `--rm`
flag removes it automatically on exit).
