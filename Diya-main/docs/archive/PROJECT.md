# Diya Meditation Kiosk — Project Overview (ARCHIVED — superseded)

> **This document is retired.** It describes an earlier architecture
> (in-app QuestPDF report generation, `CalibrationView`/`MeditationView`/
> `ReportView` screens, `ISensorSource`/`ICameraSource`/`IMotorController`
> hardware interfaces, hardware partner referred to as "IITH team") that no
> longer matches the code. Kept here only as a historical record.
>
> For current scope and architecture, see **`docs/responsibilities.md`**
> and **`docs/Diya-Codebase-Overview.pdf`**.

A full record of what this project is, the decisions behind it, what's been built,
what's planned, and where everything currently lives.

> For install / run / deploy commands, see **SETUP.md**.
> For a Q&A walkthrough of how it works, see **FAQ.md**.

---

## 1. What this is

**Diya** is an unattended **meditation kiosk** for a public/museum-style setting. A
visitor walks up, is identified, goes through a short guided session while
cameras/sensors observe them, and receives a report at the end. The machine then
resets itself for the next person.

**Intended visitor flow:**

```
IDLE / Welcome  →  IDENTIFY (QR or details)  →  CALIBRATION  →  GUIDED MEDITATION  →  REPORT  →  back to IDLE
```

**Scope split:**
- **Us:** the Linux desktop application, the UI/UX, the registration system, packaging, and the integration layer.
- **IITH team:** the hardware/computer-vision side (RealSense / thermal cameras, servo motors, sensor data). We built clean interfaces so their code plugs in later with no UI changes.

---

## 2. Tech stack & key decisions

| Area | Choice | Why |
|---|---|---|
| Language / runtime | **C# / .NET 8 LTS** | Managed memory + GC → fewer crash classes for an all-day unattended machine. |
| UI framework | **Avalonia 11.2.3** | Cross-platform desktop UI that officially supports **Linux** (MAUI does not). |
| Target OS | **Ubuntu 26.04** (Wayland/GNOME) | Deployment target; single session, no X11. |
| Backend (online mode) | **Node.js + Express + Postgres** | Simple, hosted easily on Render's free tier. |
| PDF reports | **QuestPDF** (Community licence) | Pure-managed, works headless on Linux, no external tools. |
| QR (in-app) | **QRCoder** (`PngByteQRCode`) | No `System.Drawing` dependency; Linux-safe. |
| Excel (offline mode) | **ClosedXML** | Reads `.xlsx` headless on Linux. |

**Why not Electron / C++ / a pure web app:** the hard part is native sensor/motor
work. Electron would still need a native sidecar + browser overhead; C++ trades GC
safety for no real perf gain in UI + CV orchestration; a pure web app can't drive
local hardware on an offline kiosk. A single native managed app is the simplest
thing that can run unattended all day.

---

## 3. Kiosk behaviour (lock-down)

- Launches **fullscreen**, frameless, always-on-top, no taskbar.
- **Cannot be closed** by users — the window close event is vetoed in code.
- **Secret exit:** `Ctrl + Shift + Alt + Q` (chosen to avoid GNOME defaults).
- `ShutdownMode = OnExplicitShutdown` — the app survives even if the window closes.
- **Auto-restart** on crash (systemd user service, `Restart=always`).
- **Auto-start** on boot (autostart `.desktop` + automatic login).
- GNOME shortcuts that could escape the kiosk are disabled (`setup-kiosk.sh`).

### Fullscreen gotchas discovered (Wayland/GNOME)
1. **`CanResize` must be `True`** — `False` sets fixed WM size-hints and mutter then *refuses* to fullscreen the window.
2. **Apply fullscreen in code, not XAML** — `WindowState="FullScreen"` in XAML doesn't stick on Wayland.
3. **Re-assert fullscreen ~6× after open** — the compositor maps the window in normal state first; a `DispatcherTimer` re-applies fullscreen at 250 ms intervals.
4. **`InvariantGlobalization=true`** — drops the libicu dependency so the `.deb` installs across Ubuntu versions.
5. **Self-contained single-file publish** — bundles the .NET runtime; target needs nothing pre-installed.
6. **Autostart needs a delay on Wayland** — `sleep 4` before launch so the session is ready.

---

## 4. The journey: how visitor identification evolved

This is the part that changed the most, so it's worth understanding the history.

### Phase 1 — Offline embedded QR (v1.0.2 → 1.1.0)
The QR **contained all the visitor data**: `DIYA1:<base64 of UTF-8 JSON {name,email,age}>`.
A registration web page generated it; the kiosk decoded it locally. Fully offline,
no backend. Parser: `Models/VisitorQr.cs`.

### Phase 2 — Online lookup (v1.2.0 → 1.3.0, on `main`)
Moved to a **hosted database**. The QR now carries only an **id**; the kiosk fetches
the visitor from an API. Two sub-flows:
- **Standalone pass:** register on the site → get a QR of the id → kiosk fetches by id (`GET /api/visitors/:id`).
- **"Model B" (the current primary):** the **kiosk shows a QR**, the **visitor scans it with their phone**, registers on their phone, and the kiosk **polls and auto-advances** when they submit. No scanner/camera needed at the kiosk.

### Phase 3 — Offline Excel variant (v1.5.0, branch only)
For deployments with **no internet**: the kiosk loads a fixed **CSV/XLSX** list of
people; a visitor is identified by **scanning their pass** (USB QR scanner) or
**typing their name**. A `PassGenerator` tool turns the list into printable QR
badges. This is an **alternative direction**, not stacked on the online one.

> **Open decision:** online (Render) vs offline (Excel) has not been finalised. They
> serve different deployment realities. See §9.

---

## 5. Architecture

### 5.1 Backend (`server/`) — online mode
Node/Express + `pg`, also serves the static registration site. Deployed on Render
(`render.yaml`: free web service + Postgres).

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | liveness check |
| `POST /api/sessions` | kiosk starts a session → `{ token }` |
| `GET /api/sessions/:token` | kiosk polls → `pending` or `claimed` + visitor |
| `POST /api/visitors` | register `{name,email,age,session?}` → `{id, linked}` |
| `GET /api/visitors/:id` | look up a standalone pass |

Tables: `visitors(id, name, email, age, created_at)` and
`sessions(token, status, visitor_id, created_at, claimed_at)`. Schema auto-created on
boot. The kiosk points at it via the **`DIYA_API_BASE`** env var.

### 5.2 Kiosk app (`DiyaMeditation/`) — the full screen flow
- **`IKioskNavigator`** (implemented by `MainWindow`) swaps the current screen inside a `ContentHost` (a `TransitioningContentControl` with a cross-fade).
- **`SessionContext`** carries the visitor + calibration result + metrics through the flow and is discarded on return to Idle.
- **Screens:** `HomeView` (identify) → `CalibrationView` → `MeditationView` → `ReportView` → back to `HomeView`.

### 5.3 Calibration (`DiyaMeditation/calibration/`)
- `camera_utils.py` — camera discovery helpers (provided by the hardware side, kept unmodified; uses `v4l2-ctl`). **Requires python3 ≥ 3.10** (`int | None` hints).
- `start_calibration.py` — the entry point the kiosk runs; imports `camera_utils` and prints status. The kiosk treats **any output** as "calibration started".
- Run by `Services/CalibrationRunner.cs` (streams the script's stdout/stderr live). Configurable via `DIYA_CALIBRATION_SCRIPT` / `DIYA_PYTHON`.

### 5.4 Meditation + hardware abstraction
- `MeditationView` shows a breathing guide + progress and samples an **`ISensorSource`** once per second.
- **`MockSensorSource`** produces a plausible "settling down" curve so the whole flow runs **before real hardware exists**.
- Plug-in interfaces for IITH: **`ISensorSource`**, **`ICameraSource`**, **`IMotorController`** (in `Services/Hardware/`). Swapping the mock for real adapters needs **no UI changes**.
- Results are computed by `MeditationMetrics.From(...)` (clamped, zero-sample safe).

### 5.5 Report PDF (`Services/ReportPdf.cs`, `Services/ReportStore.cs`)
- `ReportPdf` builds a formatted A4 report (visitor + score + calmness/focus/HR + message) with QuestPDF.
- `ReportStore` saves it to **`/opt/meditation-app/data/`** (override via **`DIYA_DATA_DIR`**; falls back to `~/.local/share/diya-meditation/data` if `/opt` isn't writable). The `.deb` postinst creates the folder writable.

---

## 6. Packaging & deployment

- **`deploy/build-deb.sh`** — builds a self-contained single-file `.deb` for `amd64` or `arm64`; falls back to `ar`/`tar` if `dpkg-deb` is absent. Depends: `libx11-6, libice6, libsm6, libfontconfig1, python3`.
- **`deploy/diya-meditation.service`** — systemd user service (auto-restart, `DIYA_API_BASE` env line).
- **`deploy/setup-kiosk.sh`** — installs + locks down GNOME, enables lingering/autologin.
- **`docker/`** — preview-only path (Xvfb → noVNC) to view the UI in a browser; **not** the real deployment.
- **`registration/index.html`** — the phone/standalone registration page (session-aware).
- **`tools/PassGenerator/`** — offline tool that turns a people list into printable QR passes (offline mode).

> **Note:** the build currently **commits the `.deb` binaries** into `package/`. This
> bloats the repo; a CI pipeline producing GitHub Releases is the intended fix (§9).

---

## 7. Version history

| Version | What |
|---|---|
| 1.0.2 / 1.1.0 | Offline embedded-QR; QR visitor pass; UI restyle |
| 1.2.0 | Online lookup (QR = id, kiosk fetches by id) |
| 1.3.0 | **Model B** — kiosk shows QR, phone registers, kiosk auto-advances |
| 1.4.0 | Calibration launch (Python script) + manual email/age fields |
| 1.5.0 | **Offline Excel variant** (CSV/XLSX list + pass generator) — separate branch |
| 1.6.0 | **Full screen flow** (Calibration → Meditation → Report → Idle) + hardware mocks |
| 1.7.0 | Report saved as **PDF** to `/opt/meditation-app/data/` |
| 1.7.1 | **UX polish** (cross-fade, decluttered welcome, calmer calibration/meditation) |

> The version string lives in a few places (`MainWindow` log line, `SETUP.md`, the
> build arg). Centralising it is a known cleanup (§9).

---

## 8. Branch & PR map (current state)

| Branch | PR | Contains | Status |
|---|---|---|---|
| `main` | — | Online Model B + registration + packaging | canonical |
| `feature/calibration-and-manual-fields` | #7 | Calibration runner + email/age fields | open; **superseded by #9** |
| `feature/offline-excel-passes` | #8 | Offline CSV/XLSX variant + pass generator | open; **alternative direction** |
| `feature/full-screen-flow` | #9 | Full flow (Calibration→Meditation→Report) + PDF; includes #7 | open; **main product line** |
| `feature/ux-improvements` | #10 | UX polish on top of #9 | open; **review only** |
| `docs/project-overview` | this | PROJECT.md + FAQ.md | docs |

**Relationships:** #9 includes #7. #10 builds on #9. #8 is a standalone alternative.
The live Render backend is already deployed and working.

---

## 9. Known limitations & open decisions

1. **Direction not finalised:** online (Render) vs offline (Excel). Pick one as canonical and consolidate the branches.
2. **No real hardware yet:** meditation uses `MockSensorSource`; calibration just runs the script. Real IITH camera/servo/sensor adapters are the big remaining milestone.
3. **No consent/privacy screen** — a kiosk with cameras observing people likely needs one before deployment (ethical/often legal).
4. **Meditation media** is a built-in breathing animation; no audio/voiceover assets yet.
5. **Render free tier** sleeps after ~15 min idle (first request cold-starts ~30–50 s); free Postgres is deleted after 30 days (use Neon/Supabase for persistence).
6. **Repo hygiene:** `.deb` binaries committed to git; version string duplicated; headless test project not committed → all candidates for a CI setup.
7. **Branch fragmentation:** several open PRs with overlapping version history.

---

## 10. Roadmap (suggested order)

1. **Consolidate** the canonical direction and merge/close stale branches.
2. **Consent/privacy screen** before calibration.
3. **Persist session results** (Render DB) + a small **admin dashboard**.
4. **Global inactivity reset** (return to Idle if a visitor walks away mid-flow).
5. **Real IITH hardware adapters** via the existing interfaces.
6. **Guided audio** for the meditation.
7. **CI** to build `.deb`s → GitHub Releases (stop committing binaries); single source of truth for the version.

---

## 11. Testing done

- Backend session flow E2E (against in-memory Postgres).
- Real kiosk **client** flow E2E (CreateSession → register → Claimed → NotFound).
- Metrics edge cases (zero samples, clamping, negative duration), message thresholds.
- `MockSensorSource` range/trend; `CalibrationRunner` (missing script + real script).
- Report PDF generation (valid PDF, null metrics, unicode names, data-dir fallback).
- **Headless construction** of every screen + `MainWindow` + navigation transitions.
- QuestPDF + Avalonia **SkiaSharp coexistence** verified (same 2.88.9, runs together).

> Not covered automatically: pixel-level visual appearance and animations — these
> need an eyes-on check on a real display / VM.
