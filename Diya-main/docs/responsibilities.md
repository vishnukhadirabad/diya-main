# Diya — Responsibilities & Scope

Diya is an unattended meditation kiosk built across **three collaborating
parties**: us (this repo), a hardware/CV team, and a face-recognition/
registration team. This file states who owns what — both today, and where
the project is headed.

> `PROJECT.md`, `FAQ.md`, `server/`, `registration/`, and `render.yaml` have
> all been **retired** (moved to `docs/archive/`, see
> `docs/archive/README.md`). `PROJECT.md`/`FAQ.md` described an earlier,
> abandoned architecture (in-app QuestPDF report generation,
> `CalibrationView`/`MeditationView`/`ReportView` screens,
> `ISensorSource`/`ICameraSource`/`IMotorController` hardware interfaces,
> partner referred to as "IITH team"). `server/`/`registration/`/
> `render.yaml` were the Node/Express backend and web pages behind the
> QR/phone-claim flow, superseded by face recognition (see §1 below). None
> of that exists in the current code. Trust this file and
> `docs/Diya-Codebase-Overview.pdf` for current scope and architecture.

---

## 1. Current state — what we own today

- **Kiosk desktop app** (`DiyaMeditation/`, C#/.NET 8 + Avalonia) — the
  fullscreen on-screen experience: shows a live camera preview and identifies
  the visitor via face recognition (`Services/IdentifyRunner.cs` runs the
  vendored `vendor/am-mock-client/client.py --kiosk-identify` — local YuNet
  detection + sface embedding, only the resulting vector crosses the network),
  freezes on the matched frame and shows their name, auto-runs the pipeline,
  renders the resulting report PDF on-screen, resets for the next visitor. The
  UI owns the camera (so the preview has no lag) and streams frames to the
  Python client for detection. A manual name/email entry stays as a fallback
  if the camera can't identify someone.
- **The identify integration** — the kiosk calls the face-recognition team's
  identify backend directly (`POST /api/v1/identify/`, configured via
  `DIYA_IDENTIFY_SERVER_URL`). There is **no Diya-owned backend** — see §4.
- **Packaging & deployment** (`deploy/`) — builds the kiosk as a
  self-contained `.deb` (`deploy/build-deb.sh`), systemd service setup.

## 2. Current state — explicitly not ours

- **Camera/servo/CV Python scripts** (`HOME1`/`SHOOT1`/`CHEST1`/`EYE1`,
  invoked by `scripts/run1.sh`) — hardware team.
- **The external `meditation-app`** (separate `.deb`, separate repo) — runs
  the actual meditation session and writes the report PDF — hardware team.

Boundary: `scripts/run1.sh` is the editable pipeline entry point; the
handoff directory is `/opt/meditation-app/data`, where `meditation-app`
writes the report PDF and our app reads the newest one. Our app only
launches the pipeline and renders whatever PDF comes out — no involvement
in CV or meditation logic.

## 3. Reference pattern for the identify integration

Two sibling repos on disk prototype the shape of the identify integration
implemented in `Services/IdentifyRunner.cs` +
`vendor/am-mock-client/client.py`:

- `am-mock-server` — FastAPI mock of `am-master-server`. Registers a face
  photo → stores an embedding. `POST /api/v1/identify/` matches a
  submitted face vector against stored embeddings (sface = 128-dim,
  auraface = 512-dim; never mixed).
- `am-mock-client` — the edge/kiosk-side client (`Am-FaceRecognition-Client`):
  captures a camera frame, detects + embeds the face (YuNet detector +
  sface/auraface embedder), calls the server's identify endpoint. Rather than
  duplicating this client, the kiosk vendors it as a **git submodule** at
  `DiyaMeditation/vendor/am-mock-client` and drives its `client.py`
  `--kiosk-identify` mode: a headless watch-until-match that prints one JSON
  result line (`{"matched", "name", "email", "confidence", "distance"}`) and
  exits. `IdentifyRunner.cs` launches it with `--frames-stdin` and feeds it
  camera frames captured by the UI (so the on-screen preview stays lag-free),
  reusing the client's existing detect → embed → identify pipeline unchanged.

Current end-to-end flow:

```
Kiosk camera captures face
  -> identify call (face-recognition team's backend, POST /api/v1/identify/)
  -> match found -> visitor identified (no phone/QR step)
  -> calibration runs (scripts/run1.sh: HOME1 -> SHOOT1 -> CHEST1 -> EYE1, unchanged)
  -> launches external meditation-app (hardware team, unchanged)
  -> meditation-app writes report PDF to /opt/meditation-app/data (unchanged)
  -> kiosk renders report on-screen (unchanged)
  -> [future phase] report emailed/texted to visitor
  -> reset for next visitor
```

## 4. Ownership boundaries

- **Diya-main (us):** kiosk app, the identify-*consuming* integration,
  calibration trigger, meditation-app launch, report render, packaging.
- **Hardware team:** CV/servo scripts, `meditation-app`.
- **Face-recognition/registration team:** face enrollment/registration
  backend (`am-master-server` in production; `am-mock-server` is the local
  mock/reference). **We do not build or own registration** — Diya-main only
  calls the identify endpoint.

## 5. Open items

Carried over from `docs/Diya-Codebase-Overview.pdf` (§11), still relevant:

- **Window management** — the external `meditation-app` needs to own the
  screen for the whole session; our app doesn't yet yield to it, and a
  stray terminal window currently appears.

  The terminal window is **not ours**, and a static search has already ruled
  out the obvious suspects — don't redo it:
  - No terminal emulator is referenced anywhere in this repo (`.cs`, `.sh`,
    `.desktop`, `.service` all clean). `PipelineRunner.cs` and
    `IdentifyRunner.cs` both use `UseShellExecute=false`,
    `CreateNoWindow=true` with all streams redirected;
    `deploy/diya-meditation.desktop` has `Terminal=false`.
  - Nothing in `/opt/meditation-app` references one either — its shell
    scripts are clean and a `strings` scan of all 12 binaries in `bin/` and
    `depth_bin/` found nothing.
  - `meditation-app` ships no `.desktop` file at all (`dpkg -L`), so a
    `Terminal=true` desktop entry is not the cause.

  **A full instrumented run on 2026-07-27 did not reproduce it.** Every step
  (`mpv` → `Front` → `splitSide` → `splitGaze` → `adjustment_test_updated` →
  `feh` → `acquisition` → `morphing` → `output_analysis` → `5M` → `ffplay` →
  `t3`) was traced for 11.5 minutes with a new-pty watch and a process-table
  diff: **zero new ptys, zero terminal processes**. So `meditation-app` does not
  open a terminal on this machine; the cause is most likely how it is launched
  on the hardware machine. See `docs/hardware-team-bugs.md` §9.

  To identify it there, run **`scripts/trace-terminal.sh`** (as root) on the
  hardware machine and reproduce the window. Note that the obvious
  `execsnoop-bpfcc | grep -iE "terminal|xterm|konsole"` **returns nothing on
  Ubuntu 24.04+** — the default terminal is `ptyxis`, which that pattern does
  not match, and single-instance GApplications open a new window over D-Bus
  with no `execve` for `execsnoop` to see. `trace-terminal.sh` handles both.
- **No timeout on `run1.sh`'s retry loop** — a permanently failing
  camera/script would hang the kiosk with no error screen.
- **No consent/privacy screen** — cameras are used and (today) Aadhaar
  numbers are stored, with nothing shown to the visitor about it.
- **No inactivity auto-reset** — a visitor walking away mid-session leaves
  the kiosk stuck.
- **`client.py --kiosk-identify`'s watch loop never gives up on a genuine
  no-match** — it only returns on a match or a fatal error (missing
  model/camera), so an unenrolled visitor relies on the kiosk's manual
  name/email fallback to proceed; there's no "give up after N seconds"
  behavior.
- **Report email/SMS delivery** — confirmed requirement, deferred. The
  identify response already carries an `email` field (currently unpopulated
  by `am-mock-server`) that a future email-delivery phase can build on.
