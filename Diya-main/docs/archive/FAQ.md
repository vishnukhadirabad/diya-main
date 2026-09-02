# Diya Meditation Kiosk — FAQ / Knowledge Base (ARCHIVED — superseded)

> **This document is retired.** Most of it (identification flow, navigation,
> calibration, report generation, hardware interfaces) describes the same
> earlier architecture as `docs/archive/PROJECT.md` and no longer matches
> the code. Kept here only as a historical record.
>
> For current scope and architecture, see **`docs/responsibilities.md`**
> and **`docs/Diya-Codebase-Overview.pdf`**.

Common questions about **what** this project is, **how** it works, and **where** the
code lives. Aimed at a new developer or stakeholder getting up to speed.

---

## Q1. What does this project actually do, end to end?

It's an unattended **meditation kiosk**. A visitor is identified, does a short guided
session while cameras/sensors observe them, gets a report, and the kiosk resets for
the next person:

```
Welcome/Identify → Calibration → Guided Meditation → Report → back to Welcome
```

- **Identify:** scan a QR with your phone and register (online mode), or scan a pre-printed pass / type your name (offline mode).
- **Calibration:** runs a Python script that (eventually) aligns the cameras/servo.
- **Meditation:** a breathing guide + timer while sensor data is gathered.
- **Report:** a session score (calmness/focus/heart rate), shown on screen and saved as a PDF.

The **app** (C#/Avalonia) is ours; the **camera/servo/CV hardware** is the IITH team's
and plugs in through interfaces we defined.

---

## Q2. Why C# + .NET + Avalonia instead of Electron, Flutter, or a web app?

- The hard requirement is driving **native sensors and motors** on an offline Linux
  kiosk. A pure web app can't do that. Electron could, but only with a native sidecar
  plus browser overhead.
- **C#/.NET** gives managed memory + garbage collection → fewer crash classes for a
  machine running all day unattended. Performance is plenty for UI + CV orchestration.
- **Avalonia** is the cross-platform .NET UI framework that **officially supports
  Linux** (Microsoft's MAUI does not). It renders with Skia and runs on Wayland/GNOME.

Net result: a single self-contained native app, simplest thing that runs unattended.

---

## Q3. How does visitor identification work — what's in the QR code?

There are **two modes** (and a legacy one):

**Online "Model B" (current primary, on `main`):**
1. The **kiosk** calls `POST /api/sessions` and gets a short **token**.
2. It displays a **QR** encoding `https://<site>/?session=<token>`.
3. The **visitor scans it with their phone**, which opens the registration page; they enter name/email/age and submit (`POST /api/visitors` with the token).
4. The kiosk **polls** `GET /api/sessions/:token` every 2 s; when it sees `claimed`, it pulls the visitor's details and advances. **No scanner/camera needed at the kiosk.**

**Offline mode (`feature/offline-excel-passes`):**
- The kiosk loads a fixed **CSV/XLSX** list. The QR holds only an **id**; a **USB QR scanner** types it in (or the visitor types their name), and the kiosk looks the id up in the local file. No internet.

**Legacy (Phase 1):** the QR contained the whole visitor record as `DIYA1:<base64 JSON>`,
decoded locally (`Models/VisitorQr.cs`).

So today the QR carries either a **session token** (online) or a **short id** (offline) —
never personal data.

---

## Q4. How does navigation between screens work in the code?

- `MainWindow` implements **`IKioskNavigator`** (`Services/IKioskNavigator.cs`) with
  `GoToHome / GoToCalibration / GoToMeditation / GoToReport`.
- Each call sets `ContentHost.Content = new <Screen>View(this, context)`. `ContentHost`
  is a **`TransitioningContentControl`** with a `CrossFade`, so screens fade between
  each other.
- A **`SessionContext`** object (`Models/SessionContext.cs`) is created when a visitor
  is identified and carried into every screen. It holds the `VisitorData`, the
  calibration result, and the `MeditationMetrics`. It's dropped when the kiosk returns
  to Idle.
- Each screen is a `UserControl` that does its job and then calls `navigator.GoTo...`.
  Screens stop their own timers on `Unloaded` to avoid leaks.

---

## Q5. How does calibration work, and how is the Python script integrated?

- Files live in `DiyaMeditation/calibration/`:
  - `camera_utils.py` — camera discovery (uses `v4l2-ctl`); **provided by the hardware side and kept unmodified**. Needs **python3 ≥ 3.10**.
  - `start_calibration.py` — the entry point the kiosk runs; imports `camera_utils` and prints status lines (the "serial" feed). This is where real hardware logic goes later.
- `Services/CalibrationRunner.cs` launches `python3 start_calibration.py`, **streams its stdout/stderr live** to the Calibration screen, and reports success if it produced **any output**.
- Configurable without rebuilding: `DIYA_CALIBRATION_SCRIPT` (path) and `DIYA_PYTHON` (interpreter).
- The scripts are bundled next to the app and into the `.deb` at
  `/opt/diya-meditation/calibration/`. To change calibration: edit the scripts and
  re-run `build-deb.sh` (see SETUP.md §"Update the calibration script & repackage").

---

## Q6. Where do reports come from, and where are they stored?

- After the meditation, `MeditationMetrics.From(...)` computes the score from the
  accumulated sensor samples (clamped 0–100, safe against zero samples).
- `Services/ReportPdf.cs` builds a formatted A4 PDF with **QuestPDF** (Community
  licence, pure-managed, works headless on Linux).
- `Services/ReportStore.cs` saves it to **`/opt/meditation-app/data/`** by default.
  Resolution order: `DIYA_DATA_DIR` env → `/opt/meditation-app/data` → 
  `~/.local/share/diya-meditation/data` → a temp folder (so it never silently fails).
  The `.deb` postinst creates `/opt/meditation-app/data` writable.
- QuestPDF and Avalonia both use SkiaSharp; we verified they resolve to the **same
  version (2.88.9)** and run together in one process without conflict.

---

## Q7. How is it packaged and deployed as a locked-down kiosk?

- **`deploy/build-deb.sh`** produces a **self-contained single-file `.deb`** (bundles
  the .NET runtime) for `amd64` or `arm64`. It uses `dpkg-deb`, or an `ar`/`tar`
  fallback if that's unavailable.
- **systemd user service** (`deploy/diya-meditation.service`) auto-starts and
  auto-restarts the app and carries the `DIYA_API_BASE` env var.
- **`deploy/setup-kiosk.sh`** installs it, enables lingering + autologin, and disables
  GNOME shortcuts that could let a visitor escape.
- **Lock-down in app code** (`Views/MainWindow.axaml.cs`): fullscreen is applied in
  `OnOpened` and re-asserted ~6×; the close event is vetoed; `OnExplicitShutdown`
  keeps the app alive; the only exit is **`Ctrl+Shift+Alt+Q`**.
- **Online backend** is deployed on **Render** from `render.yaml` (a free web service +
  Postgres). The kiosk just needs `DIYA_API_BASE` pointed at the service URL.

---

## Q8. How will the real IITH hardware plug in without rewriting the UI?

Through three interfaces in `Services/Hardware/`:

- **`ISensorSource`** — `Start() / Read() / Stop()`, returns a `SensorSample(Calmness, Focus, HeartRate)`. The meditation screen reads it once per second.
- **`ICameraSource`** — camera lifecycle (calibration + meditation).
- **`IMotorController`** — servo positioning (calibration).

Today these are backed by **`MockSensorSource`** (a smooth, plausible curve) so the
whole flow runs end-to-end before any hardware exists. When IITH delivers their
scripts/APIs, we write **adapter classes** that implement these interfaces and swap
them in — the screens, navigation, metrics, and report code **don't change**. The
calibration Python hook (`start_calibration.py`) is the matching plug point for the
camera/servo bring-up.

---

## Quick reference

| I want to… | Look at |
|---|---|
| Understand the whole project | `docs/responsibilities.md` |
| Install / run / deploy | `SETUP.md` |
| Change the API endpoints | `server/server.js` |
| Change a screen's look | `DiyaMeditation/Views/*.axaml` |
| Change navigation/flow | `Views/MainWindow.axaml.cs` + `Services/IKioskNavigator.cs` |
| Change calibration behaviour | `DiyaMeditation/calibration/start_calibration.py` |
| Change the report/PDF | `Services/ReportPdf.cs`, `Services/ReportStore.cs` |
| Plug in real hardware | `Services/Hardware/ISensorSource.cs` (+ a real adapter) |
| Point the kiosk at the API | `DIYA_API_BASE` env var |
| Build a `.deb` | `deploy/build-deb.sh <version> <amd64|arm64>` |
