# Diya Meditation Kiosk — Code-Grounded System Analysis

**Investigation date:** 2026-08-16
**Method:** Direct source inspection + one full end-to-end execution of Architecture A on live hardware.
**Machine:** `bharataap-MS-7D90`, Ubuntu (Wayland/GNOME), Linux 7.0.0-29-generic.

**Evidence labels used throughout:**

| Label | Meaning |
|---|---|
| **CONFIRMED** | Directly verified in source, or observed during live execution |
| **INFERRED** | Strongly implied by code, not explicitly proven |
| **UNKNOWN** | Cannot be determined from the repository |
| **OUTDATED** | Reference documentation says X; code does Y |
| **STUB** | Code exists but performs no real work |

---

## 1. Executive Summary

The `diya ` folder contains **two independent, mutually disconnected kiosk implementations** that both aim to deliver the same visitor experience (identify a person → run a guided meditation with multi-camera biometric capture → show a PDF report).

| | **Architecture A — `Diya-main`** | **Architecture B — `latest_A`** |
|---|---|---|
| Orchestrator | C# Avalonia app → `run1.sh` | `kiosk_run.sh` (bash) |
| Calibration stages | `mark1/` — **STUB** (print & exit 0) | `HOME4/SHOOT3/trigger_y/CHEST4/EYE4` — **real** |
| Motor / Arduino control | **None** | Full serial protocol, 2 axes |
| Radar presence sensing | **None** | LD2410 mmWave |
| Face recognition | Vendored client, stdin frame streaming | Same client, `--camera` + `person_detail.txt` |
| Meditation stage | `meditation_gui_updated` (source) | `meditation-app` (the `.deb`) |
| **Runs on this machine today** | **YES — verified end-to-end** | **NO — 5 hard blockers** |

**The single most important finding:** these two systems share **no code path whatsoever**. Architecture A's real hardware calibration is stubbed out; Architecture B has the real hardware calibration but cannot execute here. Neither is a complete production system on its own right now.

**The single most important safety finding:** `CHEST4.py` and `EYE4.py` have **no overall alignment timeout**. If a person is present but the alignment error never converges to within ±8 px, the control loop streams motor commands **indefinitely** with a person seated in the rig. Details in §24/§25.

---

## 2. System Purpose

An unattended, museum-style meditation kiosk ("like an ATM", per `Diya-main/docs/responsibilities.md`). A visitor approaches, is identified by face, is physically aligned to sensors by a motorised rig, sits through a guided meditation while thermal / gaze / depth / posture data is captured, and receives a personalised PDF report on screen.

Three separate teams own pieces (**CONFIRMED** — `Diya-main/docs/responsibilities.md`):

1. **Diya team** — kiosk shell UI, identify integration, meditation launch, report render, packaging. *Explicitly owns no backend.*
2. **Hardware team** — the CV/servo calibration scripts and the `meditation-app` `.deb`.
3. **Face-recognition team** — the identify/enrollment backend (`am-master-server` in production, `am-mock-server` as the local mock).

---

## 3. Complete User Journey (as actually implemented in Architecture A)

**CONFIRMED by live execution on 2026-08-16, 10:09:28 → 10:20:06 (10 min 38 s).**

1. Kiosk sits fullscreen on the home screen, camera preview live.
2. Visitor stands in front of the C920. Every 3rd frame is streamed to the identify client.
3. Face matched → green **MATCHED** overlay (observed: `VISHNUKUMAR`, confidence 0.69, distance 0.615).
4. Kiosk releases the camera (225 ms) and spawns the pipeline.
5. Calibration stages run — **in reality these are stubs and complete in 0.6 s total.**
6. 1-minute meditation video plays fullscreen (mpv, `ONE_MINS.mp4`).
7. Four camera stages run (`run_stages.py`) holding the RealSense and Arducam.
8. Black screen; ~5-minute acquisition with 4 parallel capture processes.
9. Playback of generated clips (ffplay) while the PDF report is built in background.
10. Report published to `/opt/meditation-app/data/`; kiosk renders it in-app.
11. **Return** resets for the next visitor (observed: a second session auto-started with a different visitor, `teja v`).

---

## 4. High-Level Architecture

```
                    ┌──────────── ARCHITECTURE A (operational) ────────────┐
   Visitor ──▶ C920 ──▶ DiyaMeditation (C#/Avalonia, fullscreen kiosk)
                          │  stdin: 4-byte BE length + JPEG
                          ▼
                        client.py --kiosk-identify  (YuNet + SFace 128-dim)
                          │  POST /api/v1/identify/  (vector only, never pixels)
                          ▼
                        am-mock-server (FastAPI :8000, SQLite, L2 ≤ 0.8)
                          │  matched
                          ▼
                        run1.sh ──▶ mark1/*.py  [STUB — no work]
                          │
                          ▼
                        frontback1 (meditation_gui_updated)
                          ├─ mpv 1-min video
                          ├─ run_stages.py  (4 camera stages)
                          ├─ acquisition    (4 parallel captures, ~5 min)
                          └─ t3.py ──▶ PDF ──▶ /opt/meditation-app/data
                                                 │
                          ReportRenderer (PDFium) ◀┘  displays in-app

                    ┌──────────── ARCHITECTURE B (not runnable here) ──────┐
   kiosk_run.sh ──▶ HOME4.py ──▶ SHOOT3.py ──▶ trigger_y.py ──▶ CHEST4.py ──▶ EYE4.py
                       │            │              │               │            │
                       └────────────┴──────────────┴───────────────┴────────────┘
                                    │ all speak serial 115200 to one Arduino
                                    │ trigger_y speaks 256000 to LD2410 radar
                                    ▼
                        client.py --camera ──▶ person_detail.txt ──▶ meditation-app
```

---

## 5. Repository Structure (actual)

```
/home/bharataap/Desktop/diya /          ← note: trailing space in dir name
├── Diya-main/                   git repo, no remote (detached HEAD 4a6cb76)
│   ├── DiyaMeditation/          C# .NET 8 Avalonia kiosk, v1.5.0
│   │   ├── Program.cs           entry point, single-instance lock
│   │   ├── Views/               MainWindow (kiosk shell), HomeView (all UI states)
│   │   ├── Services/            IdentifyRunner, PipelineRunner, ReportRenderer
│   │   ├── Models/VisitorData.cs
│   │   ├── scripts/run1.sh      the Architecture-A pipeline orchestrator
│   │   ├── vendor/am-mock-client/  git submodule (self-contained client.py)
│   │   ├── deploy/              build-deb.sh, setup-kiosk.sh, systemd unit
│   │   └── docker/              UI-preview only (Xvfb + noVNC)
│   ├── docs/                    plan.md, responsibilities.md, hardware-team-bugs.md
│   │   └── archive/             retired QR/phone flow (Node/Express + Postgres)
│   └── package/                 prebuilt .deb (amd64 + arm64)
├── am-mock-client/              git: IIITH-CVIT/am-mock-client @ c84dda5
│   └── face_client/             importable package (detection/embedders/db/server)
├── am-mock-server/              git: IIITH-CVIT/am-mock-server @ fd875c4
│   ├── app/                     FastAPI app, routers, face_engine
│   ├── dist/mock-server         prebuilt PyInstaller binary (143 MB)
│   └── data/db.sqlite           16 registrations, sface 128-dim
├── latest_A/                    git: EshwarTeja-17/latest_A @ 492cdc1 ("Add files via upload")
│   ├── kiosk_run.sh             Architecture-B orchestrator
│   ├── HOME4.py SHOOT3.py trigger_y.py CHEST4.py EYE4.py   ← the REAL hardware stages
│   ├── camera_utils.py ld2410_config.py
│   ├── face_client/             fork of am-mock-client's package
│   │   ├── pipeline.py          + kiosk confirm-streak / timeout / person_detail.txt
│   │   └── prev_pipeline.py     byte-identical backup of the unforked version
│   ├── log_file_check log_file_failure  ← real field-run logs
│   └── person_detail.txt        "eshwar@1" (stale leftover)
├── mark1/                       HOME1/SHOOT1/CHEST1/EYE1  ← ALL STUBS
└── deb/                         unpacked meditation-app .deb payload (hardware team)
    ├── opt/meditation-app/      frontback1, acquisition, bin/, depth_bin/, data/
    ├── usr/local/bin/meditation-app   2-line launcher
    └── etc/udev/rules.d/99-realsense-libusb.rules
```

Two additional trees live **outside** this folder and are load-bearing:

- `~/Desktop/meditation_gui_updated/` — the meditation stage **run from source** (what Architecture A actually executes).
- `/opt/meditation-app/` — the installed `.deb` (what Architecture B's `meditation-app` command launches).

---

## 6. Actual Entry Point

**CONFIRMED — there is no automatic entry point on this machine.** Verified absent:

| Mechanism | Result |
|---|---|
| `~/.config/systemd/user/` | only an empty `default.target.wants/` |
| `systemctl --user list-unit-files \| grep -i diya\|kiosk\|meditat` | **none** |
| `systemctl --user is-active diya-meditation` | **inactive** |
| `~/.config/autostart/` | **does not exist** |
| `/etc/systemd/system/` diya/kiosk units | **none** |
| `crontab -l` | **empty** |
| `/etc/rc.local` | **does not exist** |

So both architectures are **manually launched**. This contradicts `SETUP.md` / `deploy/setup-kiosk.sh`, which describe a `diya-meditation.service` user unit with `Restart=always` and `loginctl enable-linger`. **Status: OUTDATED** — the deployment docs describe an autostart configuration that is not installed here.

**Architecture A launch (verified working):**

```bash
cd "/home/bharataap/Desktop/diya /Diya-main/DiyaMeditation/bin/Debug/net8.0" && DOTNET_ROOT="/home/bharataap/.dotnet" DISPLAY=":0" XAUTHORITY="/run/user/1000/.mutter-Xwaylandauth.XGGHU3" DIYA_PIPELINE_WORK_DIR="/home/bharataap/Desktop/diya /mark1" ./DiyaMeditation
```

Two environment fixes are mandatory and neither is documented:

1. **`DOTNET_ROOT`** — the apphost resolves to `/usr/lib/dotnet`, which only has .NET 10.0.10. The app targets net8.0; .NET 8.0.29 lives in `~/.dotnet`. Without this the app exits immediately with *"You must install or update .NET"*. **CONFIRMED by observation.**
2. **`XAUTHORITY` + local X grant** — `run_stages.py` imports `pyautogui` → `mouseinfo` → `Xlib`, which fails with *"Authorization required, but no authorization protocol specified"* when launched from a non-session shell. Notably `xdpyinfo` succeeds with the mutter auth file while python-Xlib still rejects it; the working fix was `xhost +SI:localuser:bharataap`. **CONFIRMED by observation — this killed the first run attempt right after the video started.**

**Architecture B launch (per its own header):** `chmod +x kiosk_run.sh && ./kiosk_run.sh` — manual, foreground, `Ctrl+C` to terminate.

---

## 7. Complete Execution Flow — Architecture A

Every transition below was observed in the live run.

| # | Step | Mechanism | Success condition | Observed |
|---|---|---|---|---|
| 1 | `Program.cs` | `flock` on `/tmp/diya-meditation.lock` (`DIYA_LOCK_FILE`) | lock acquired | ✓ |
| 2 | `MainWindow` | Avalonia fullscreen; `DispatcherTimer` re-asserts fullscreen every 250 ms → 2 s | window at 1920×1080 | ✓ |
| 3 | `HomeView.StartCameraAsync` | FlashCap V4L2, selects camera by name `C920` (`DIYA_CAMERA_NAME`) | preview frames | ✓ |
| 4 | `IdentifyRunner` | spawns `python3 vendor/am-mock-client/client.py --kiosk-identify --frames-stdin --max-unmatched 45` | process alive | ✓ |
| 5 | frame pump | every 3rd frame, 4-byte big-endian length + JPEG to child stdin; capacity-1 drop-oldest channel | — | ✓ |
| 6 | identify | YuNet detect → SFace 128-dim → `POST /api/v1/identify/` | JSON line on stdout | `Matched: VISHNUKUMAR (confidence=0.692 distance=0.615)` |
| 7 | `ParseLastJsonLine` | reads last stdout line into `IdentifyResult` | `matched=true` | ✓ 10:09:28.276 |
| 8 | MATCHED overlay | UI state swap | — | ✓ 10:09:28.707 |
| 9 | **camera release** | full FlashCap teardown **before** spawn | camera freed | ✓ 225 ms, 10:09:28.933 |
| 10 | `PipelineRunner` | `bash scripts/run1.sh`, **no timeout** | exit 0 | ✓ |
| 11 | run1.sh stages | `python3 HOME1.py` … `EYE1.py` from `DIYA_PIPELINE_WORK_DIR` | each exit 0 | ✓ all 4 in 0.6 s (**stubs**) |
| 12 | meditation stage | `bash ./frontback1` in `meditation_gui_updated`, venv prepended to PATH | exit 0 | ✓ 10:20:06.871 |
| 13 | `publish_report` | newest `*.pdf` → `.part` → atomic rename into `DIYA_REPORT_DIR` | file written | ✓ 10:20:06.962, 23,248,830 bytes |
| 14 | `ReportRenderer` | PDFtoImage/PDFium + SkiaSharp → Avalonia bitmaps | pages rendered | PDF valid (`%PDF-1.3`, clean `%%EOF`) |

### Step 9 is the critical one

**CONFIRMED (code comment + observed timing).** FlashCap opens `/dev/video0` **without `O_CLOEXEC`**. If the camera is not fully released before `run1.sh` is spawned, forked children inherit the file descriptor, pin the camera, and every downstream stage that tries to open it hangs forever. The release is deliberately kept synchronous on the critical path.

### The meditation stage internals (`~/Desktop/meditation_gui_updated/frontback1`)

```
mpv --fs --no-border --ontop --no-osc  ONE_MINS.mp4   &  (MPV_PID)
python3 run_stages.py --after-pid $MPV_PID     ← 4 camera stages in ONE process
feh -F black_background_1920x1080.png          &  (BLACK_PID)
bash acquisition
   ├─ check_similarity4.py   (posture / Arducam)   ┐
   ├─ visual_test6.py        (gaze / C920)         │ 4 parallel, ~5 min
   ├─ depthacquisition.py    (RealSense depth)     │
   └─ test2_time.py          (thermal / USB cam)   ┘
   ├─ morphing.py  &  5M.py   (parallel)
   ├─ t3.py  (PDF, nice -n 10, waits on the 4 output videos)
   └─ bash output_analysis    (ffplay playback, ~200 s)
kill $BLACK_PID
```

Two deliberate latency optimisations are documented in-file and **CONFIRMED**: `run_stages.py` replaced four separate python processes (which cost 4.2 s of black screen in interpreter startup + MediaPipe construction + cold camera opens) with one process holding cameras open across stage boundaries (~0.6 s); and `t3.py` now runs *during* playback rather than after it, removing ~9 s of dead black screen.

---

## 8. Execution Flow — Architecture B (`kiosk_run.sh`)

**CONFIRMED from source.** Sequence, retry semantics, and logging:

```
outer while true:                                  ← restart target
  for script in HOME4.py SHOOT3.py trigger_y.py CHEST4.py EYE4.py:
      python3.10 -u "$script" 2>&1 | tee -a log_file_check
      EXIT=${PIPESTATUS[0]}            ← tee always exits 0, so $? would hide failures
      if EXIT != 0: log to BOTH logs; exit EXIT     ← FATAL, no retry
  (cd $CAMERA_CLIENT_DIR && $CAMERA_CLIENT_PYTHON client.py --camera)
      if EXIT != 0: FATAL, no retry                ← client crashed
  PERSON=$(head -n1 $PERSON_DETAIL_FILE | tr -d '[:space:]')
  if PERSON empty or "error-person": log FACE NOT CONFIRMED; continue  ← restart from HOME4
  break
$MEDITATION_APP_CMD
  if EXIT != 0: FATAL
```

| Property | Value | Status |
|---|---|---|
| Interpreter | `python3.10 -u` (hardcoded) | CONFIRMED |
| `CAMERA_CLIENT_DIR` | `$HOME/Desktop/am-mock-client-1.1.0` (marked "EDIT THIS") | CONFIRMED |
| `MEDITATION_APP_CMD` | `meditation-app` (marked "EDIT THIS") | CONFIRMED |
| Log rotation | every `CLEAN_EVERY_N_RUNS=10` invocations via `.kiosk_run_count` + `EXIT` trap | CONFIRMED |
| `SIGINT` trap | logs which step was running to both logs, `exit 130` | CONFIRMED |
| Concurrency guard | **none** (no `flock`) — single instance assumed | CONFIRMED |

**Asymmetry worth noting:** a hardware step failing is *fatal* (kiosk dies, needs an operator), but a face not being recognised triggers an *infinite* retry loop back through homing and the actuator sequence. There is no attempt cap on the outer loop — `RETRY_COUNT` is only logged, never compared against a limit. **CONFIRMED.**

---

## 9. Hardware Architecture

### 9a. Cameras — present and enumerated on this machine (**CONFIRMED**)

| Device | Name | Role | Used by |
|---|---|---|---|
| `/dev/video0,1` | HD Pro Webcam C920 | face recognition; gaze | DiyaMeditation (FlashCap), `visual_test6.py`, `EYE4.py` |
| `/dev/video2,3` | USB Camera | thermal | `test2_time.py` |
| `/dev/video4–9` | Intel RealSense D435 | depth | `depthacquisition.py`, `splitSide`, `splitGaze` |
| `/dev/video10,11` | Arducam 8MP | front / posture | `check_similarity4.py`, `CHEST4.py` |

RealSense confirmed on USB: `Bus 001 Device 010: ID 8086:0b07 Intel Corp. RealSense D435`.

### 9b. Motion / sensing hardware — required by Architecture B, **ABSENT on this machine**

| Component | Purpose | Controlled by | Comms | Present? |
|---|---|---|---|---|
| Arduino (VID `2341`, `/dev/ttyACM*`) | drives both axes, reads switches | all 5 stage scripts | serial 115200 8N1 | **NO** — no `ttyACM*`, no `2341` on USB |
| Motor M1 | chest axis | `HOME4` (home), `SHOOT3` (fire), `CHEST4` (servo) | `E:<v>` | **NO** |
| Motor M2 | eye axis | `HOME4`, `SHOOT3`, `EYE4` | `F:<v>` | **NO** |
| M1 home limit switch | pins 5 & 6 (NO+NC pair) | Arduino firmware | `LIMIT:M1_HOME` | **NO** |
| M2 home limit switch | pins 7 & 8 (NO+NC pair) | Arduino firmware | `LIMIT:M2_HOME` | **NO** |
| Collision limit switch | pins 3 & 4 | Arduino firmware | `COLLISION:ACTIVE/CLEAR` | **NO** |
| Collision prox (early warning) | analog A0 | Arduino firmware | `EARLY:COLLISION_PROX_A0` | **NO** |
| M1 / M2 prox sensors | A1 / A2 | Arduino firmware | `EARLY:Mn_HOME`, `FAULT:PROXn_REPLACE` | **NO** |
| LD2410C mmWave radar (CP2102, VID `10C4`/PID `EA60`) | seat presence | `trigger_y.py` | serial 256000 | **NO** — no `/dev/serial/by-id`, no `10c4` on USB |

**Pin mapping source:** `COMPONENT_LABELS` dict, consistent across `HOME4.py`, `CHEST4.py`, `EYE4.py`. **CONFIRMED.**

### 9c. The switch/prox design rationale (**CONFIRMED**, documented in `HOME4.py`)

Home limit switches are wired as an **NO+NC pair** specifically so they are *provably* testable — a self-test can distinguish "switch open" from "wire cut" from "shorted". Proximity sensors are **not** provable this way. The design compensates: if a prox sensor dies silently, the mechanical switch catches the lever that the prox should have caught first, and the firmware reports `FAULT:PROXn_REPLACE` → the software halts with "PROX n NOT DETECTED — REPLACEMENT REQUIRED". This is a genuinely thoughtful failure-detection design and is the strongest safety feature in the codebase.

---

## 10. Arduino Communication

### 10a. Link parameters (**CONFIRMED**)

| Parameter | Value | Source |
|---|---|---|
| Baud | `115200` | `BAUD_RATE`/`BAUD` in all 4 scripts |
| Read timeout | `2` s | `serial.Serial(..., timeout=2)` |
| Write timeout | `1.0` s | `write_timeout=1.0` (`WRITE_TIMEOUT_S`) |
| Min gap between writes | `0.025` s (25 ms hard floor) | `_MIN_WRITE_GAP`, HOME4 |
| Port discovery | VID `2341`, or description contains "arduino", or path contains `ttyACM`; falls back to any `ttyACM*` | `find_arduino()` — inlined separately in each script |
| Reset | DTR bounce, settle `0.6` s + `0.25` s post-buffer-clear (SHOOT3); `0.5`/`0.2` (EYE4) | `DTR_SETTLE_S`, `POST_DTR_SETTLE` |

### 10b. Command vocabulary — Python → Arduino (**CONFIRMED**, extracted from every serial write)

| Command | Sent by | Meaning | Expected response | Timeout |
|---|---|---|---|---|
| `OK` | HOME4, SHOOT3, CHEST4, EYE4 | handshake ACK after `READY` | (none) | — |
| `SELFTEST?` | all four | run limit-switch self-test | `SELFTEST:BEGIN` … `TEST:k=v` … `SELFTEST:PASS\|FAIL` … `SELFTEST:END` | 5.0 s |
| `STATUS?` | all four | manual-stop switch state | `SWITCH:PRESSED\|RELEASED` | 3.0 s (watchdog) |
| `CSTATUS?` | all four | collision switch state | `COLLISION:ACTIVE\|CLEAR` | 3.0 s |
| `PSTATUSC?` | SHOOT3, CHEST4, EYE4 | early-warning collision prox (A0) | `PROXC:CLEAR` (or not-clear) | 3.0 s |
| `HSTATUS1?` / `HSTATUS2?` | HOME4, CHEST4, EYE4 | is axis physically at home? | `HOME1:AT_HOME\|AWAY\|FAULT` | 3.0 s |
| `PSTATUS1?` / `PSTATUS2?` | CHEST4, EYE4 | per-axis prox state | (prox status line) | 3.0 s |
| `home1` / `home2` | HOME4 | full homing pass | `DONE:HOME1` / `ERROR:HOMING1_*` | 30 s, 2 retries |
| `gohome1` / `gohome2` | HOME4 | fast confirm-only (already at home) | `DONE:GOHOME1` | 30 s |
| `shoot m1` / `shoot m2` | SHOOT3 | fire actuator | `shoot success` | **60 s** |
| `E:<int>` | CHEST4 | chest-axis PID error term | (none — streamed) | ~30 Hz |
| `F:<int>` | EYE4 | eye-axis PID error term | (none — streamed) | ~30 Hz |
| `STOP` | all four | emergency halt | (none) | fire-and-forget |

The `E:` vs `F:` prefix is how the firmware knows which axis's control loop to drive. **CONFIRMED.**

### 10c. Response vocabulary — Arduino → Python (**CONFIRMED**)

```
READY                       SYSTEM:READY
SELFTEST:BEGIN|PASS|FAIL|END        TEST:<key>=<value>
DONE:HOME1|HOME2|GOHOME1|GOHOME2
ERROR:HOMING1_NO_HOME_FOUND | HOMING1_SWITCH_FAULT | HOMING1_MANUAL_STOP | HOMING1_COLLISION_PROX
ERROR:HOMING2_*  (same four)        ERROR:SELFTEST_FAILED
ERROR:SHOOT1_MANUAL_STOP | SHOOT2_MANUAL_STOP | SHOOT*_COLLISION_PROX
FAULT:M1_SWITCH_ABSENT|SHORT|WIRE   FAULT:M2_SWITCH_ABSENT|SHORT|WIRE
FAULT:COLLISION_SWITCH_ABSENT|SHORT FAULT:PROX1_REPLACE | PROX2_REPLACE
LIMIT:M1_HOME | M2_HOME             EARLY:M1_HOME | M2_HOME | COLLISION_PROX_A0
COLLISION:ACTIVE | CLEAR            HOME1:AT_HOME|AWAY|FAULT   HOME2:...
SWITCH:PRESSED | RELEASED           PROXC:CLEAR                "shoot success"
```

### 10d. Communication cycle

```
Python main thread ──write──▶ Arduino ──▶ motor/actuator
                                  │
                              sensors (switches, prox)
                                  │
Python serial_reader thread ◀─────┘ (daemon, parses every line into events/queue)
                                  │
              collision_event / _stop_event / msg_queue  ──▶ main loop reacts
```

Each script runs a **dedicated daemon reader thread**. `CHEST4.py` additionally implements a **reconnecting** reader: on serial failure it retries up to `MAX_RETRIES = 3` with 2 s delays, re-scans the port (in case `/dev/ttyACMn` re-enumerated), and on success performs a **full re-handshake** via `wait_for_post_reconnect_ready()` — then re-checks collision state, halting if a collision is found active after reconnect. **CONFIRMED.**

**Architectural weakness:** the Arduino handshake/self-test/watchdog logic is **re-implemented independently in all five scripts** rather than shared. `camera_utils.py` is the only genuinely shared module (camera + LD2410 + Arduino port resolution). This means a protocol fix must be applied in five places. **CONFIRMED.**

---

## 11. Homing System — `HOME4.py`

**Why it exists:** stepper/servo axes have no absolute position feedback at power-on. Homing drives each axis until a known mechanical reference (the home limit switch) triggers, establishing the zero point that all later moves — including the alignment servo loops — are relative to. Without it, `E:`/`F:` corrections would be applied from an unknown origin. **INFERRED** (rationale not stated in-file, but standard and consistent with the code).

### Startup gate sequence (**CONFIRMED**)

1. Auto-detect Arduino → DTR reset → open port.
2. Wait for `READY`; reply `OK`.
3. `run_limit_switch_selftest()` → `SELFTEST?`; abort on `SELFTEST:FAIL` or any `FAULT:*_SWITCH_*`.
4. `wait_for_switch_released()` → `STATUS?`; if the manual-stop switch is held, display `pause.png` fullscreen and block until released.
5. `check_initial_collision()` → `CSTATUS?`; abort if already in collision.
6. Start watchdog thread: ping `STATUS?` every `WATCHDOG_INTERVAL = 5.0` s; **two consecutive missed replies** (`WATCHDOG_REPLY_TIMEOUT = 3.0` s each) → `emergency_stop`.
7. Per axis: `HSTATUS{n}?` → if `AT_HOME` send `gohome{n}` (fast confirm), else `home{n}` (full pass).
8. `send_command_with_retry()` waits up to `TIMEOUT = 30` s for `DONE:*`/`ERROR:*`, retrying up to `MAX_HOME_RETRIES = 2` — but **only** on `RESULT_RETRY`, which is returned specifically when the operator pressed manual-stop mid-move. An intentional pause is therefore not treated as a failure.

### Exit codes (**CONFIRMED**)

| Code | Meaning |
|---|---|
| `0` | normal completion |
| `1` | Arduino not found |
| `2` | `HARDWARE_FAULT_EXIT_CODE` — limit-switch fault, home-not-found, prox replacement needed, or motor homing failure |

`HOME4.py:24` carries a revealing comment: *"Set this to 0 if run1.sh does not check the exit status and you don't want the pipeline to abort here."* This is the **only** textual link between the two architectures anywhere in the codebase — the hardware team wrote `HOME4.py` aware of Diya's `run1.sh`, but **no code wires them together**. **CONFIRMED.**

### Real observed failures

`log_file_failure` records `HOME4.py` exiting **code 2** twice on 2026-08-14 (17:18:04 and 17:32:44), with `log_file_check` showing `ERROR:HOMING1_NO_HOME_FOUND` → *"M1 (CHEST) HOME NOT FOUND — HOMING ABORTED"* and *"Motor 1 home not found within configured travel"*. This is a real, reproduced field failure. **CONFIRMED.**

---

## 12. Actuator / Shoot System — `SHOOT3.py`

**What "shoot" means physically: UNKNOWN.** The code fires an actuator per axis and waits for the firmware to report `shoot success`. Nothing in the repository states what is physically actuated (deployment of a sensor arm, a shutter, a probe, etc.). This cannot be determined from the source and requires hardware documentation or the Arduino firmware, which is **not in this repository**.

### Flow (**CONFIRMED**)

1. Connect + DTR reset (`DTR_SETTLE_S = 0.6`, `POST_DTR_SETTLE = 0.25`).
2. `wait_for_ready()` — `READY` within `READY_TIMEOUT_S = 15.0`, ACK `OK`, then await `SYSTEM:READY`.
3. `run_selftest()` — `SELFTEST?`, require `SELFTEST:PASS` within `SELFTEST_TIMEOUT_S = 5.0`. **Refuses to proceed otherwise.**
4. `check_collision_prox()` — `PSTATUSC?`, require `PROXC:CLEAR`. *(Proactive A0 check, newer than the equivalent in HOME4.)*
5. `send_shoot(ser, "m1")` → `shoot m1`, await `shoot success` within `SHOOT_TIMEOUT_S = 60.0`.
6. `send_shoot(ser, "m2")` → same for M2.
7. Any failure → send `STOP`, `sys.exit(1)`. Whole lifecycle in `try/finally` to always close the port.

Handled error responses: `ERROR:SELFTEST_FAILED`, `SWITCH:PRESSED`, `COLLISION:ACTIVE`, `ERROR:SHOOT*_COLLISION_PROX`, `FAULT:*`, `SHOOT_LOCKED`.

**Reference doc claim "approximately 60 seconds" → CONFIRMED exactly: `SHOOT_TIMEOUT_S = 60.0`.**
Order is strictly M1 then M2, sequential, never parallel. **CONFIRMED.**
`SHOOT3.py` imports no `cv2` — it has no UI at all, unlike the other three. **CONFIRMED.**

Real observed failure: `log_file_failure` shows `SHOOT3.py` exit code 1 once on 2026-08-14. **CONFIRMED.**

---

## 13. Person Detection — `trigger_y.py` + `ld2410_config.py`

Runs **third**, between the actuator sequence and camera alignment — it blocks until a person is confirmed seated, so the alignment cameras never start against an empty seat.

### Verified constants (**all CONFIRMED**)

| Constant | Value | Purpose |
|---|---|---|
| `BAUD_RATE` | `256000` | LD2410C default |
| `SEAT_DISTANCE_MM` | `850` | sensor → seat distance |
| `SEAT_TOLERANCE_MM` | `200` | → accept band **650–1050 mm** |
| `CONFIRM_SECONDS` | `5` | continuous in-band presence required |
| `REQUIRE_MOTION_BLIP` | `True` | ≥1 motion event during the hold |
| `EXIT_DEBOUNCE_FRAMES` | `5` | frames out-of-band before resetting the timer |
| `ENABLE_RANGE_CAPPING` | `True` | cap radar range on-device at startup |
| `RANGE_CAP_MARGIN_MM` | `200` | cap at `SEAT_MAX_MM + 200` |
| `NO_ONE_DURATION_S` | `2` | radar's own no-target hold |
| `GATE_SIZE_MM` / `MAX_GATE_INDEX` | `750` / `8` | 9 gates ≈ 6.75 m |
| `DISTANCE_CHANGE_THRESHOLD_MM` | `50` | jitter suppression |

**The reference documentation's "850 mm ± 200 mm" and "5 continuous seconds" are both CONFIRMED exactly.**

### Why the design is the way it is

- **Range capping** (`ld2410_config.py`) uses a *different protocol* from the streaming data frames: command frames are `FD FC FB FA` / `04 03 02 01`, data frames are `F4 F3 F2 F1` / `F8 F7 F6 F5`. The radar **stops streaming target data while in config mode**, so `enter_config_mode()`/`end_config_mode()` must bracket any configuration. Capping the gate on-device means distant people never register *at the hardware level* — a stronger filter than software distance checks. Failure to configure is **non-fatal** (logs a warning, continues with existing config). **CONFIRMED.**
- **`REQUIRE_MOTION_BLIP`** distinguishes a living seated person from a static object left on the seat — a bag would hold distance but produce no motion energy. **CONFIRMED.**
- **`EXIT_DEBOUNCE_FRAMES = 5`** prevents single-frame multipath/ghosting glitches from resetting a nearly-complete 5-second hold. **CONFIRMED.**
- A documented bug-fix: energy-0 "ambiguous" frames are now treated as **neutral** rather than as "person left", because the previous fallback distance was unreliable. **CONFIRMED.**
- In-file caveat: a standing-person field log showed the sensor **under-reporting** distance versus pure slant geometry (sensor at 770 mm height, seat at 450 mm, horizontal gap 800–900 mm) — so the band is empirically tuned, not purely geometric. **CONFIRMED.**

### Failure behaviour — a gap

`trigger_y.py` has **no timeout and no non-zero exit path** other than `Ctrl+C` or a serial exception. If nobody ever sits down, it waits **forever**, and `kiosk_run.sh` blocks on it indefinitely. On success it prints `"Person is in front of the KIOSK"` and returns 0. **CONFIRMED — this is a significant liveness gap for an unattended kiosk.**

---

## 14. Chest Alignment — `CHEST4.py`

**File:** `latest_A/CHEST4.py` · **Camera:** Arducam via `camera_utils.get_camera_index("arducam")` · **Model:** MediaPipe Pose (`mp.solutions.pose.Pose()`) · **Axis:** M1 · **Status: CONFIRMED**

*(The reference documentation's `align_chest()` function name does **not** exist — the loop is inline in the main body around lines 1300–1400. Labelled **OUTDATED**.)*

### The mathematics (verified verbatim, `CHEST4.py:1305–1352`)

```python
h1, w1, _ = frame1.shape
center_y1 = h1 // 2                          # camera optical centre (vertical)

lm = res1.pose_landmarks.landmark
x1,y1_lm = lm[11].x*w1, lm[11].y*h1          # left shoulder
x2,y2_lm = lm[12].x*w1, lm[12].y*h1          # right shoulder
x3,y3    = (x1+x2)//2, (y1_lm+y2_lm)//2      # shoulder midpoint

x4,y4_lm = lm[23].x*w1, lm[23].y*h1          # left hip
x5,y5_lm = lm[24].x*w1, lm[24].y*h1          # right hip
x6,y6    = (x4+x5)//2, (y4_lm+y5_lm)//2      # hip midpoint

x7,y7    = (x3+x6)//2, (y3+y6)//2            # TORSO CENTRE
error_chest = center_y1 - y7                 # signed pixel error
```

So the torso centre is the **midpoint of (shoulder midpoint, hip midpoint)** — landmarks **11, 12, 23, 24**. The error is a signed vertical pixel offset: positive when the torso sits below the optical centre.

### The closed loop

```
Arducam frame ─▶ MediaPipe Pose ─▶ torso centre y7
                                        │
                    error = center_y1 - y7
                                        │
                    send_error() ──▶ "E:<error>\n" ──▶ Arduino  (≈30 Hz, send_interval=0.03)
                                        │
                              firmware drives M1
                                        │
                    next frame observes new position ──┘   (repeat)
```

Python computes only the **error term**; the actual PID/step logic lives in Arduino firmware that is **not in this repository**. Direction logic, step size, and gains are therefore **UNKNOWN** from this codebase.

### Termination

| Condition | Action | Status |
|---|---|---|
| `-8 <= error_chest <= 8` | write `Alined_CHEST_.jpg`, overlay "ALIGNED", send `E:0`, hold display 3 s, exit | CONFIRMED |
| no person for `NO_PERSON_TIMEOUT = 5.0` s | send `E:0`, shutdown | CONFIRMED |
| collision mid-loop | `show_collision_and_exit()` → `send_error(0)` → shutdown | CONFIRMED (line 1275) |
| early collision prox mid-loop | `show_collision_prox_and_exit()` → shutdown | CONFIRMED (line 1279) |
| frame grab failure | `shutdown("Frame grab failed")` | CONFIRMED |
| **error never converges, person present** | **loops forever, motor keeps moving** | **CONFIRMED — no timeout exists** |

**Reference doc claim "±8 pixels" → CONFIRMED exactly.** There is **no** maximum-attempts counter and **no** overall alignment timeout. See §24.

### UI
Split-screen window `Chest_Check`: `chest_reference_left.png` (target pose) on the left, live annotated feed on the right, via `make_combined()`. Startup gates before the loop: self-test → `STATUS?`/`CSTATUS?` → `PSTATUSC?` → `check_hardware_faults()` → `check_m1_home_at_startup()` (if M1 reports `AT_HOME` at this stage it means *wrong camera/axis indices* and the run aborts).

---

## 15. Eye Alignment — `EYE4.py`

**File:** `latest_A/EYE4.py` · **Camera:** Logitech C920 via `get_camera_index("logitech")`, `CAP_V4L2`, **MJPG**, **640×480 @ 15 fps**, `CAP_PROP_BUFFERSIZE=1` · **Model:** `cvzone.FaceMeshModule.FaceMeshDetector(maxFaces=1)` · **Axis:** M2 · **Status: CONFIRMED**

### The mathematics (verified verbatim, `EYE4.py:1320–1332`)

```python
face = detector.findFaceMesh(img, draw=False)
mid_point_eyes = face[168]                   # MediaPipe FaceMesh landmark 168 = glabella
error_eye = center_y1 - mid_point_eyes[1]    # signed vertical pixel error
if -8 <= error_eye <= 8 and not image_captured:
    cv2.imwrite("Alined_EYE_.jpg", ...)
```

**Reference doc claim "landmark 168" → CONFIRMED exactly.** Landmark 168 is the point between the eyes (glabella / nasion region), a stable single-point proxy for eye level — simpler and less jittery than averaging both iris centres.

Structurally identical to `CHEST4.py` but: uses `F:<value>` instead of `E:<value>`, gates on M2 (`HSTATUS2?`/`PSTATUS2?`, `check_m2_home_at_startup()`), displays `Eye_Check` with `eye_reference_left.png`, and holds the post-alignment display **4 s** (vs. chest's 3 s).

`EYE4.py` carries extra `FIX-N`-numbered hardening beyond `CHEST4.py`: DTR settle tuned to 0.5 s/0.2 s, all raw writes routed through a lock-guarded `_locked_write()`, port re-scan on reconnect in case `/dev/ttyACMn` re-enumerates, and an `os.devnull` stderr redirect around `cap.release()` to suppress noisy V4L2 shutdown warnings. **CONFIRMED.**

**Same missing overall timeout as CHEST4.**

---

## 16. Camera Initialization & Latency

**Architecture B** opens and releases cameras **per stage** — `CHEST4.py` opens the Arducam, aligns, releases; `EYE4.py` then opens the C920, aligns, releases; then `client.py --camera` opens a camera again. Each open pays V4L2 negotiation, MediaPipe/cvzone model construction, and sensor warm-up. **CONFIRMED** — this is inherent to the one-process-per-stage design.

**Architecture A explicitly solved this problem** in the meditation stage. From `frontback1`'s own comments (**CONFIRMED**): four separate python processes each paid "interpreter startup, ~1 s of imports, MediaPipe model construction and a cold camera open before its first frame reached the screen, while the stage before it paid librealsense teardown — **4.2 s of black screen** across the sequence". `run_stages.py` runs the same four scripts in one process with cameras held open across boundaries, reducing this to **~0.6 s**. It is also started *alongside* the video (`--after-pid $MPV_PID`) so imports and camera warm-up happen while the visitor is still watching.

Architecture B has **not** received this optimisation. Whether that matters depends on whether a visitor is watching during alignment — **UNKNOWN**.

Architecture A's other camera concern is ownership, not latency: the C# app must fully release the C920 before spawning children (§7, step 9).

---

## 17. Face Recognition

Both architectures use the **same recognition core**: YuNet detection (`cv2.FaceDetectorYN`, native OpenCV 5) → SFace embedding (`cv2.FaceRecognizerSF`, **128-dim**, L2-normalised) → vector POSTed to the server. AuraFace R100 (512-dim, `aurar100.onnx`, via onnxruntime) is the configurable alternate. **Client and server must agree on the embedder — the server matches purely by vector dimension.** **CONFIRMED.**

`aurar100.onnx` is **absent from disk** in both `am-mock-client/models/` and `latest_A` (gitignored, ~250 MB). Only the sface path is usable today. **CONFIRMED.**

### Server matching (`am-mock-server`)

| Property | Value |
|---|---|
| Endpoint | `POST /api/v1/identify/` (form-encoded, `type=face`, `face_vector` as comma-joined `%.6f`) |
| Search | brute-force linear scan, normalised L2, dimension-gated |
| Match threshold | `0.8` (distance ≤ 0.8) |
| Confidence | `max(0.0, 1.0 - distance/2.0)` |
| Storage | SQLite `data/db.sqlite`; **16 registrations**, all sface/128-dim |

The server **never derives embeddings from pixels at identify time** — it only vector-searches what the client submits. Raw frames never leave the kiosk. **CONFIRMED** (a genuine privacy strength).

### The two client modes differ — this is the real fork

| | **Architecture A** (`--kiosk-identify --frames-stdin`) | **Architecture B** (`--camera`) |
|---|---|---|
| Camera owner | the C# app | the Python client |
| Frame transport | 4-byte BE length + JPEG over stdin | direct `cv2.VideoCapture` |
| Give-up rule | `--max-unmatched 45` (~4–5 s of an unrecognised face) | `DETECT_TIMEOUT_S = 7` s |
| Confirmation | first match wins | **5 consecutive** same-name matches |
| Result channel | JSON line on stdout | `person_detail.txt` file |

### The confirmation streak (verified, `latest_A/face_client/pipeline.py:290–423`)

```python
CONFIRM_MATCHES  = getattr(cfg, "camera_confirm_matches", 5)    # → 5
DETECT_TIMEOUT_S = getattr(cfg, "camera_detect_timeout_s", 7)   # → 7
...
if name:
    if name == last_match_name: match_streak += 1
    else: last_match_name, match_streak = name, 1
else:
    last_match_name, match_streak = None, 0      # "Unknown" RESETS
...
if last_match_name and match_streak >= CONFIRM_MATCHES:
    confirmed_name = last_match_name; break
```

**Neither `camera_confirm_matches` nor `camera_detect_timeout_s` appears in `config.yaml`** — verified by grep. Both therefore fall back to the `getattr` defaults **5** and **7**. **Reference doc's "5 consecutive matching results" → CONFIRMED (as an effective default, not as a configured value).**

### Answering the documentation's worked example explicitly

```
Frame 1 → Vishnu    streak = 1
Frame 2 → Vishnu    streak = 2
Frame 3 → Unknown   streak = 0   ← RESET (no-face / no-name branch)
Frame 4 → Vishnu    streak = 1
Frame 5 → Vishnu    streak = 2
```

**This sequence is REJECTED.** The streak requires 5 *consecutive* identifications of the same name; any `Unknown` frame — or a frame with no face at all — zeroes it. A different name also resets to 1 rather than accumulating, so a mix of two people can never confirm. **CONFIRMED.**

The design rationale is stated in-file: confidence fluctuated ~0.52–0.74 frame-to-frame in testing, so a single lucky frame must not trigger a match.

**A timing risk is flagged in the code's own comments and is real:** with `frame_skip = 10`, an identification runs only every 10th frame. Five consecutive identifications therefore need ~50 frames of *uninterrupted* recognition inside a **7-second** budget — and any single miss restarts the count. The comment recommends lowering `camera_confirm_matches` and/or `camera_frame_skip` if confirmation proves unreliable. **CONFIRMED as a design concern; real-world failure rate is UNKNOWN without runtime measurement.**

**Configuration mismatch:** `latest_A/config.yaml` sets `camera.device: 3`, whereas `am-mock-client/config.yaml` sets `0`. On *this* machine `/dev/video3` is the **USB Camera** (thermal), not the C920. Whether index 3 is correct on the kiosk rig is **UNKNOWN**, but it is certainly wrong here. **CONFIRMED as a discrepancy.**

---

## 18. Inter-Process Communication

Four distinct IPC mechanisms are in use. **All CONFIRMED.**

| # | Mechanism | Between | Direction | Notes |
|---|---|---|---|---|
| 1 | **stdin pipe, length-prefixed binary** | C# kiosk → `client.py` | frames out | 4-byte big-endian length + JPEG; zero-length = clean EOF. Capacity-1 **drop-oldest** channel means only the freshest frame is ever queued, so capture never stalls behind recognition. |
| 2 | **stdout, last-JSON-line** | `client.py` → C# kiosk | result in | `ParseLastJsonLine` reads `{"matched","name","email","confidence","distance"}` |
| 3 | **HTTP REST** | client → server | vector out, identity in | `POST /api/v1/identify/` |
| 4 | **File — `person_detail.txt`** | `client.py --camera` → `kiosk_run.sh` | result in | Architecture B only |
| 5 | **File — the report PDF** | `t3.py` → kiosk | artefact | atomic `.part` → rename |
| 6 | **`flock`** | pipeline ↔ itself | mutual exclusion | Architecture A only |

### `person_detail.txt` in detail

- **Writer:** `_write_person_detail(path, content)` in `latest_A/face_client/pipeline.py:83`, mode `"w"` (overwrite, never append), called **exactly once** per `run_camera()` in a `finally` block.
- **Path:** alongside the config file (`os.path.dirname(cfg.config_path)`), else CWD.
- **Content:** either the confirmed name, or the literal `error-person`.
- **Reader:** `kiosk_run.sh:186` — `head -n 1 | tr -d '[:space:]'`.
- **Semantics:** empty **or** missing **or** `error-person` → restart the whole sequence from `HOME4.py`; anything else → treat as a confirmed person and proceed.
- **Not written at all** when the operator presses `q` — a deliberate abort is not a detection result.

**Risks (all CONFIRMED by reading the contract):**

1. **Stale-data risk is real and is the most serious.** The file is only rewritten when `run_camera()` reaches its `finally`. If the client is killed (SIGKILL, power loss, OOM) before that, the file retains the **previous visitor's name**, and `kiosk_run.sh` will read it as a fresh success and launch the meditation app for the wrong person. There is no timestamp, no PID, no nonce, and no clearing of the file *before* the camera step.
2. **The path is split across two projects.** `kiosk_run.sh` reads `$CAMERA_CLIENT_DIR/person_detail.txt` (i.e. `~/Desktop/am-mock-client-1.1.0/`), while the writer resolves the path relative to *its own* config. These agree only if the deployed client is the one at `CAMERA_CLIENT_DIR`. The copy inside `latest_A/` (currently `eshwar@1`) is a **stale leftover** and is not what the orchestrator reads.
3. **No atomic write** — plain `open(...,"w")`, unlike the report PDF, which does use `.part`→rename. A crash mid-write could leave a truncated name. Low probability given the payload is a few bytes, but the codebase already knows the correct pattern and does not apply it here.
4. **Any name that is not `error-person` is accepted**, including a corrupted or partially-written one.

**Assessment (not a recommendation to change it):** for a strictly sequential, single-instance bash pipeline, a file is a defensible choice — it is trivially debuggable, survives process boundaries, and needs no server. An exit code could carry only pass/fail, not a name; stdout would work but would have to be disentangled from the client's copious logging. The genuine deficiency is **not** the use of a file, it is the absence of freshness guarantees. Clearing the file immediately before invoking the camera step would close the stale-data hole with one line and no architectural change.

---

## 19. `kiosk_run.sh` Orchestration

```
kiosk_run.sh  (bash, foreground, manual start, no flock)
     │
     ├─ trap rotate_logs_if_needed EXIT       ← rotate both logs every 10th invocation
     ├─ trap cleanup_on_interrupt SIGINT      ← log current step, exit 130
     │
     └─ while true:                           ← OUTER: restart target, uncapped
          ├─ HOME4.py       python3.10 -u, tee → log_file_check, PIPESTATUS[0]   ─┐
          ├─ SHOOT3.py                                                            │ any
          ├─ trigger_y.py                                                         │ non-zero
          ├─ CHEST4.py                                                            │ = FATAL
          ├─ EYE4.py                                                             ─┘
          ├─ client.py --camera  (in $CAMERA_CLIENT_DIR)  → crash = FATAL
          ├─ read person_detail.txt
          │    ├─ empty / "error-person"  →  log + `continue`  ──▶ back to HOME4
          │    └─ a name                  →  log PERSON CONFIRMED + `break`
          └─ $MEDITATION_APP_CMD  → non-zero = FATAL
```

**It is a genuine conductor** — sequential, exit-code-driven, with per-step logging. **CONFIRMED.**

What it does **not** do (**all CONFIRMED absent**):

- No `wait`/job control — every step is strictly foreground and blocking.
- No process supervision, no restart of a crashed step, no stale-process cleanup, no `pkill` of orphaned children between attempts.
- No `flock` — two concurrent invocations would fight over the Arduino and cameras.
- No cap on outer-loop retries.
- No cleanup on the fatal paths: it `exit`s without sending `STOP` to the Arduino or releasing cameras (each Python script is responsible for its own teardown, which works only if that script is the one that failed).

`PIPESTATUS[0]` is used correctly throughout — because every step is piped to `tee`, plain `$?` would always read `tee`'s exit status and silently mask every failure. This is a deliberate and correct choice. **CONFIRMED.**

---

## 20. Diya-main Architecture

**Framework:** C# / .NET 8 / Avalonia 11.2.3, version 1.5.0, single-window kiosk shell. **CONFIRMED.**

| File | Role |
|---|---|
| `Program.cs` | entry; exclusive `flock` on `/tmp/diya-meditation.lock` (`DIYA_LOCK_FILE`) so a second kiosk can't fight over cameras |
| `App.axaml(.cs)` | Fluent theme (Light); `ShutdownMode.OnExplicitShutdown` — closing the window does not quit |
| `Views/MainWindow.axaml(.cs)` | `SystemDecorations="None"`, no taskbar; `DispatcherTimer` re-asserts fullscreen every 250 ms then 2 s; swallows Alt+F4 and WM-close; **sole sanctioned exit is `q`**; `DIYA_KIOSK=0` disables lockdown |
| `Views/HomeView.axaml(.cs)` | the only real screen — all states as overlays: home/identify, MatchedOverlay, SessionBackdrop (black, hides inter-stage gaps), ReportOverlay |
| `Services/IdentifyRunner.cs` | spawns and pumps frames to `client.py`; **no timeout by design** |
| `Services/PipelineRunner.cs` | `bash scripts/run1.sh`; **no timeout by design** (run1.sh owns its own retry logic) |
| `Services/ReportRenderer.cs` | newest `*.pdf` in `DIYA_REPORT_DIR` → PDFtoImage/PDFium + SkiaSharp → Avalonia bitmaps |
| `Models/VisitorData.cs` | trivial DTO — `Name`, `Email` |

**Hardware integration: none directly.** The C# app owns exactly one device — the C920, via FlashCap (V4L2), selected **by name** (`DIYA_CAMERA_NAME`, default `"C920"`) specifically to avoid grabbing the thermal/RealSense/Arducam devices. Everything else is delegated to child processes. **CONFIRMED.**

**Does it call `latest_A` or `kiosk_run.sh`? NO.** Verified by grep across all `.cs`, `.sh`, `.axaml`, `.csproj`, `.md` files in `Diya-main` for `latest_A|kiosk_run|HOME4|SHOOT3|trigger_y|CHEST4|EYE4|ld2410|arduino|ttyACM` — **zero matches**. **CONFIRMED.**

**Is its hardware pipeline real? No — it is a STUB.** `run1.sh` invokes `mark1/HOME1.py`, `SHOOT1.py`, `CHEST1.py`, `EYE1.py`. Each is 12–13 lines, imports only `sys` and `time`, does `time.sleep(0)`, prints e.g. `[HOME1] STUB — no CV work performed`, and exits 0. `mark1/README.md` states plainly that the genuine scripts "were not present anywhere on this machine and are not in the Diya repo." Observed: all four completed in **0.6 s total**. **CONFIRMED — STUB.**

Also note `run1.sh`'s default `WORK_DIR` is `$HOME/Desktop/mark1`, which **does not exist** — the stubs live at `~/Desktop/diya /mark1`. Without `DIYA_PIPELINE_WORK_DIR` the pipeline aborts at its sanity check. **CONFIRMED.**

### Environment variables (Architecture A)

`DIYA_KIOSK`, `DIYA_LOCK_FILE`, `DIYA_CAMERA_NAME`, `DIYA_IDENTIFY_SERVER_URL`, `DIYA_IDENTIFY_PYTHON`, `DIYA_IDENTIFY_SCRIPT`, `DIYA_PIPELINE_SCRIPT`, `DIYA_PIPELINE_WORK_DIR`, `DIYA_PIPELINE_PYTHON`, `DIYA_PIPELINE_LOCK`, `DIYA_MEDITATION_DIR`, `DIYA_MEDITATION_ENTRY`, `DIYA_REPORT_DIR`, `DIYA_BASH`.

**Caveat:** `DIYA_IDENTIFY_SERVER_URL` is set into the child's environment by `IdentifyRunner.cs`, but grep shows the vendored `client.py` **never reads it** — it uses `server.url` from its own `config.yaml`. It works today only because both default to `http://localhost:8000`. Pointing the kiosk at a different server via this variable would **silently fail**. **CONFIRMED — latent bug.**

---

## 21. latest_A Architecture

**Origin:** `github.com/EshwarTeja-17/latest_A`, single commit `492cdc1` "Add files via upload" — an upload snapshot, not a development history. **CONFIRMED.**

**What it is:** the `am-mock-client` face-recognition project **plus** a hardware orchestration layer. The face-recognition core is *not* forked meaningfully:

| File | vs. `am-mock-client` |
|---|---|
| `face_client/server_client.py`, `config.py` | **byte-identical** |
| `face_client/cli.py` | identical but for a trailing newline |
| `face_client/pipeline.py` | **differs only in `run_camera()`** (confirm-streak, timeout, `person_detail.txt`) |
| `face_client/prev_pipeline.py` | **byte-identical to `am-mock-client`'s `pipeline.py`** — a rollback snapshot |
| `config.yaml` | identical but for `camera.device` (3 vs 0) |

**Added, not present in `am-mock-client`:** `kiosk_run.sh`, `HOME4.py`, `SHOOT3.py`, `trigger_y.py`, `CHEST4.py`, `EYE4.py`, `camera_utils.py`, `ld2410_config.py`, reference/alert images, and the field logs.

**Third-party imports across the five hardware scripts** (**CONFIRMED**, exhaustive):
`cv2`, `numpy` (HOME4/CHEST4/EYE4) · `mediapipe` (CHEST4) · `cvzone` (EYE4) · `serial`, `serial.tools.list_ports` (all five). No `pyrealsense2`, no GPIO library — **all motion is via serial to the Arduino**.

**Note on `cv2` in `HOME4.py`:** it is used **only** to draw fullscreen text/alert overlays (`SYSTEM HALTED`, `LIMIT SWITCH FAULT`, `HOME NOT FOUND`, `PROX n NOT DETECTED`, collision screens). There is no vision processing in the homing stage. **CONFIRMED.**

**Orphaned asset:** `emergency_stop_img1.png` is referenced **nowhere** in the repository (verified by full-repo grep) — dead weight, possibly an alert screen that was never wired in. **CONFIRMED.**

---

## 22. Diya-main vs latest_A — Direct Comparison

| Area | **Diya-main (A)** | **latest_A (B)** |
|---|---|---|
| UI | C#/Avalonia fullscreen kiosk, overlays, in-app PDF viewer | OpenCV windows per stage; no unified shell |
| Orchestration | C# `PipelineRunner` → `run1.sh` (flock, per-stage retry) | `kiosk_run.sh` (no lock, fatal-on-failure, uncapped outer retry) |
| Hardware control | **none** | Arduino serial, 2 axes, switches, prox |
| Motor control | **none** | `home1/2`, `gohome1/2`, `shoot m1/m2`, `E:`/`F:` servo streams |
| Radar | **none** | LD2410 seat presence, on-device range capping |
| Camera | C920 owned by C# (FlashCap), released before spawn | per-stage `cv2.VideoCapture` (Arducam, C920) |
| Face recognition | stdin frame streaming, first-match, `--max-unmatched 45` | `--camera`, 5-consecutive-match streak, 7 s budget |
| Result channel | stdout JSON | `person_detail.txt` |
| Meditation stage | `meditation_gui_updated` **from source** | `meditation-app` (**the .deb**) |
| Report display | rendered **in-app** (PDFium) | **none** — hands off to the app and ends |
| Calibration | **STUB** | **real** |
| Packaging | `.deb` + systemd unit + kiosk setup script | none — bare scripts |
| Runs here today | **YES (verified)** | **NO** |

### Are they connected?

**No. They are entirely independent. CONFIRMED by three independent checks:**

1. **Grep from A → B:** no `.cs`/`.sh`/`.axaml`/`.csproj`/`.md` file in `Diya-main` mentions `latest_A`, `kiosk_run`, `HOME4`, `SHOOT3`, `trigger_y`, `CHEST4`, `EYE4`, `ld2410`, `arduino`, or `ttyACM`. **Zero matches.**
2. **Grep from B → A:** exactly **one** hit — a *comment* in `HOME4.py:24`: *"Set this to 0 if run1.sh does not check the exit status…"*. This proves shared intent, not shared execution. No `latest_A` file imports, invokes, or path-references anything in `Diya-main`.
3. **`kiosk_run.sh` points elsewhere entirely:** `CAMERA_CLIENT_DIR="$HOME/Desktop/am-mock-client-1.1.0"` — a **third** checkout that is neither `Diya-main/DiyaMeditation/vendor/am-mock-client` nor this folder's `am-mock-client`, and which **does not exist on this machine**.

They also **cannot** run simultaneously: both would drive the C920 and the meditation stage, and `run1.sh`'s `flock` protects only against a second copy of *itself*.

### Which one controls the hardware?

**Neither, right now.** Architecture A is the only one that runs here, and its calibration stages are stubs. Architecture B has the real motor/radar control but is blocked (§27). The motorised rig described in `latest_A` has therefore **never been exercised by the Diya kiosk app** — only by `kiosk_run.sh` on the hardware team's own machine, as the field logs show.

---

## 23. Meditation Application Handoff

The two architectures hand off to **different** implementations of the same experience.

| | Architecture A | Architecture B |
|---|---|---|
| Target | `~/Desktop/meditation_gui_updated/frontback1` | `/opt/meditation-app/frontback1` (via `meditation-app`) |
| Invocation | `bash ./frontback1` with venv prepended to `PATH` | `meditation-app` → `exec /opt/meditation-app/frontback1` |
| Stages | mpv → `run_stages.py` → `acquisition` → `t3.py` | mpv → `Front`→`splitSide`→`splitGaze`→`adjustment_test_updated` → `acquisition` → `t3` |
| Form | Python source | compiled binaries |
| Camera indices | **auto-detected by name** (`paths.py`) | **baked in at compile time** |
| Report | published to kiosk dir + rendered in-app | written to `/opt/meditation-app/data`, not displayed by any kiosk |

**The source version is the correct one on this machine**, and `run1.sh`'s comments say so explicitly: *"The meditation stage now runs from source (meditation_gui_updated) instead of the packaged meditation-app .deb."* The reason is decisive and verifiable:

`~/Desktop/meditation_gui_updated/paths.py` resolves cameras **by name with a numeric fallback**:
```python
FRONT_CAM_INDEX   = _camera_index('FRONT_CAM_INDEX',   'Arducam',            8)
GAZE_CAM_INDEX    = _camera_index('GAZE_CAM_INDEX',    'HD Pro Webcam C920', 0)
THERMAL_CAM_INDEX = _camera_index('THERMAL_CAM_INDEX', 'USB Camera',         10)
```
whereas the `.deb`'s `CAMERA_CONFIG.txt` documents hardcoded `THERMAL=0, GAZE=2, FRONT=4`. On this machine `/dev/video4` is the **RealSense**, not the front camera — the packaged binaries would open the wrong devices. **CONFIRMED.**

`run1.sh` bridges the resulting gap: `t3.py` writes the PDF into `MEDITATION_DIR`, but the kiosk reads `/opt/meditation-app/data`, so `publish_report()` copies it across via `.part`→rename. Without this the kiosk would display whatever stale PDF the `.deb` install left behind. **CONFIRMED — and observed working: the Aug-1 baseline was replaced by the freshly generated 23.2 MB report.**

---

## 24. Safety Mechanisms

### Present and genuinely good (**all CONFIRMED**)

| Mechanism | Implementation |
|---|---|
| **Emergency stop** | `emergency_stop()` — sends `STOP\n`, sleeps 0.3 s to let motors halt, closes serial, destroys windows, exits. Trapped on **SIGINT and SIGTERM**. |
| **Provable limit switches** | NO+NC wiring + `SELFTEST?` distinguishes open / cut / shorted (`FAULT:Mn_SWITCH_ABSENT\|SHORT\|WIRE`) |
| **Dead-prox detection** | a switch catching a lever the prox should have caught → `FAULT:PROXn_REPLACE` → halt with "REPLACEMENT REQUIRED" |
| **Serial watchdog** | `STATUS?` every 5.0 s; two missed 3.0 s replies → `emergency_stop` |
| **Pre-motion collision gates** | `CSTATUS?` (switch) and `PSTATUSC?` (A0 early-warning prox) checked at startup, and again after any reconnect |
| **Mid-motion collision abort** | reader thread sets `collision_event`; main loop checks it → `send_error(0)` then shutdown (`CHEST4.py:1275/1279`) |
| **Collision during post-align display** | also checked (`CHEST4.py:1400/1404`) — motion isn't assumed over |
| **Self-test gate before firing** | `SHOOT3` refuses to shoot unless `SELFTEST:PASS` **and** `PROXC:CLEAR` |
| **Manual-stop switch** | blocks with a fullscreen `pause.png` until released; treated as `RETRY`, not failure |
| **Wrong-index guard** | if an axis reports `AT_HOME` when alignment starts, the run aborts rather than servoing from a bad origin |
| **Write pacing** | 25 ms hard floor between serial writes; `write_timeout=1.0` so writes never block forever |
| **Reconnect + re-handshake** | `CHEST4` retries 3×, re-scans the port, full re-handshake, re-checks collision |
| **Single-instance (A only)** | `flock` on the kiosk app and on `run1.sh` |

### Missing or weak

| # | Gap | Severity | Evidence |
|---|---|---|---|
| **S1** | **No overall alignment timeout in `CHEST4.py`/`EYE4.py`.** Only `NO_PERSON_TIMEOUT=5.0` (fires when *nobody* is seen). With a person present but not converging, `E:`/`F:` streams at ~30 Hz **forever**. | **HIGH** | verified: no `MAX_ATTEMPTS`, no elapsed check on the align loop |
| **S2** | **`trigger_y.py` waits forever.** No timeout, no non-zero exit path. Kiosk hangs silently if nobody sits. | **HIGH** | verified: no timeout constant, no failure exit |
| **S3** | **`emergency_stop(exit_code=0)` defaults to 0.** `sigint_handler` calls it with that default, so `Ctrl+C` during `HOME4` exits **0** — which `kiosk_run.sh` reads as success and proceeds to `SHOOT3`. (`kiosk_run.sh`'s own SIGINT trap races this.) | **HIGH** | `HOME4.py:178` signature + `sigint_handler` |
| **S4** | **Stale `person_detail.txt`** → meditation launched for the previous visitor if the client is killed before its `finally`. | **MEDIUM** | §18 |
| **S5** | **No `flock` in `kiosk_run.sh`** — two invocations would fight over the Arduino and cameras. | **MEDIUM** | verified absent |
| **S6** | **Uncapped outer retry loop** — a persistently unrecognised visitor re-runs homing + actuator firing indefinitely. | **MEDIUM** | `RETRY_COUNT` logged, never compared |
| **S7** | **No cleanup on fatal exit** — `kiosk_run.sh` exits without sending `STOP` or reaping orphans. | **MEDIUM** | verified absent |
| **S8** | **Arduino firmware is not in this repository.** All motion limits, PID gains, step sizes, and the actual travel bounds are unreviewable. | **HIGH (for audit)** | no `.ino`/`.hex` anywhere |
| **S9** | **No consent/privacy screen** despite cameras + stored identity data. | **MEDIUM** | `docs/responsibilities.md` open item |
| **S10** | **Documented `feh` leak** — if `t3` fails, the fullscreen black window is never killed → dead kiosk screen. | **MEDIUM** | `docs/hardware-team-bugs.md` |
| **S11** | **`acquisition` always exits 0** (last command is `echo`), so its failure guard is dead code → bad-data reports shown as real. | **MEDIUM** | `docs/hardware-team-bugs.md` |
| **S12** | **Children survive and hold cameras** — verified firsthand: on shutdown, every stage ignored SIGTERM and only SIGKILL released `/dev/video*`. | **HIGH** | **observed this session** |

**S1 is the headline risk.** Every other motion path in the codebase is bounded — homing has a 30 s timeout, shooting has 60 s, the watchdog has 5 s. The alignment loops, which are the *only* stage that moves a motor with a person deliberately positioned in the mechanism, are the sole unbounded ones.

**S12 is not theoretical.** During the shutdown of the verification run, `DiyaMeditation`, `run1.sh`, `frontback1`, `acquisition`, and all four capture scripts ignored SIGTERM entirely and continued holding all five cameras. Only SIGKILL cleared them. This exactly reproduces the bug already documented in `docs/hardware-team-bugs.md`.

---

## 25. State Machine

Modelled against **Architecture B** (the only one with real hardware states). Each state is labelled with its actual implementation status.

```
                    ┌──────────────────────────────────────────┐
                    ▼                                          │
  START ─▶ INITIALIZATION ─▶ HOMING ─▶ ACTUATOR ─▶ PERSON_DETECT│
             (handshake,      (M1,M2)   (shoot     (LD2410,     │
              selftest,                  m1,m2)     5 s hold)   │
              collision                                         │
              gates)                                            │
                                                    │           │
                                                    ▼           │
                                          CHEST_ALIGN ─▶ EYE_ALIGN
                                          (M1, ±8px)     (M2, ±8px)
                                                              │
                                                              ▼
                                                     FACE_RECOGNITION
                                                     (5-streak, 7 s)
                                                       │        │
                                          error-person │        │ name
                                                       └────────┼──▶ MEDITATION ─▶ END
                                     (restart entire sequence)  │
```

| State | Status | Implementation |
|---|---|---|
| `START` | **Implemented** | manual `./kiosk_run.sh` |
| `INITIALIZATION` | **Implemented** | per-script: DTR reset, `READY`/`OK`, `SELFTEST?`, `STATUS?`, `CSTATUS?`, `PSTATUSC?` |
| `HOMING` / `HOMING_SUCCESS` | **Implemented** | `home1/2` or `gohome1/2`, `DONE:HOMEn` |
| `ACTUATOR_SEQUENCE` | **Implemented** | `shoot m1` then `shoot m2` |
| `PERSON_DETECTION` / `PERSON_STABLE` | **Implemented** | `trigger_y.py`, 5 s continuous + motion blip |
| `CHEST_ALIGNMENT` / `CHEST_ALIGNED` | **Implemented** | ±8 px, writes `Alined_CHEST_.jpg` |
| `EYE_ALIGNMENT` / `EYES_ALIGNED` | **Implemented** | ±8 px, writes `Alined_EYE_.jpg` |
| `FACE_RECOGNITION` / `RECOGNIZED` | **Implemented** | 5-consecutive-match streak |
| `MEDITATION` | **Implemented** | `meditation-app` |
| `HOMING_FAILURE` | **Implemented** | exit 2, **fatal** — no recovery |
| `ACTUATOR_FAILURE` | **Implemented** | exit 1, **fatal** |
| `EMERGENCY_STOP` | **Implemented** | `STOP\n` + trapped SIGINT/SIGTERM |
| `COLLISION` | **Implemented** | switch + A0 prox, pre/mid/post-motion |
| `UNKNOWN_PERSON` | **Implemented** | `error-person` → full restart |
| `CAMERA_FAILURE` | **Partial** | frame-grab failure → shutdown; **no** frame-timeout watchdog |
| `ARDUINO_FAILURE` | **Partial** | watchdog + reconnect in CHEST4; HOME4/SHOOT3 abort outright |
| `RADAR_TIMEOUT` | **MISSING** | `trigger_y.py` waits forever |
| `CHEST_ALIGNMENT_FAILURE` | **MISSING** | no timeout / attempt cap |
| `EYE_ALIGNMENT_FAILURE` | **MISSING** | no timeout / attempt cap |
| `PERSON_NOT_DETECTED` (during align) | **Implemented** | `NO_PERSON_TIMEOUT = 5.0 s` |
| `PROCESS_CRASH` (supervision) | **MISSING** | no restart, no reaping |
| Power-failure recovery | **MISSING** | no autostart at all (§6) |

---

## 26. Failure-Mode Table

| Failure | Detection | Immediate action | Recovery | Safety risk |
|---|---|---|---|---|
| Arduino not found at start | `find_arduino()` returns none | exit 1 | operator | Low |
| Arduino disconnects mid-move | watchdog: 2× missed `STATUS?` (≤10 s) | `emergency_stop` → `STOP`, close port | fatal (HOME4/SHOOT3); CHEST4 retries 3× + re-handshake | **Medium** — up to ~10 s of uncommanded motion before detection |
| Limit switch absent/short/cut | `SELFTEST?` → `FAULT:Mn_SWITCH_*` | fullscreen fault screen, exit 2 | operator | Low (caught pre-motion) |
| Prox sensor dead | switch catches lever first → `FAULT:PROXn_REPLACE` | halt, "REPLACEMENT REQUIRED" | operator | Low (by design) |
| Collision switch active at boot | `CSTATUS?` | `show_collision_and_exit()` | operator | Low |
| Collision mid-motion | reader thread → `collision_event` | `send_error(0)` → shutdown | operator | **Medium** — depends on firmware halt latency |
| Early collision prox (A0) | `EARLY:COLLISION_PROX_A0` / `PSTATUSC?` | `show_collision_prox_and_exit()` | operator | Low |
| Motor homing timeout | 30 s, 2 retries | `ERROR:HOMINGn_NO_HOME_FOUND`, exit 2 | operator | Low — **observed twice in field logs** |
| Actuator timeout | 60 s | `STOP`, exit 1 | operator | Low — **observed once** |
| Camera unavailable | `get_camera_index()` raises | `RuntimeError` → abort | operator | Low |
| Camera stops producing frames | `ret`/`None` check | `shutdown("Frame grab failed")` | fatal | Low |
| **Alignment never converges** | **none** | **none — loops forever** | **none** | **HIGH (S1)** |
| Person leaves during alignment | `NO_PERSON_TIMEOUT = 5.0 s` | `E:0` / `F:0`, shutdown | fatal | Low |
| MediaPipe finds no landmarks | treated as "no person" | feeds the 5 s timeout | fatal | Low |
| **Radar never sees anyone** | **none** | **blocks forever** | **none** | **HIGH (S2)** |
| Radar config fails | exception caught | warn, continue uncapped | continues | Low |
| Face recognition timeout | 7 s | write `error-person` | full restart from HOME4 | Low (but re-fires actuators) |
| Unknown person | streak never reaches 5 | `error-person` | full restart | Low |
| **Stale `person_detail.txt`** | **none** | wrong name accepted | **none** | **MEDIUM (S4)** |
| Meditation app crash | non-zero exit | log, exit | operator | Low |
| Python process crash | `PIPESTATUS[0]` != 0 | log, exit | operator | Medium — no `STOP` sent |
| `Ctrl+C` during HOME4 | trapped | `emergency_stop(exit_code=0)` | **may be read as success** | **HIGH (S3)** |
| Children survive shutdown | none | none | SIGKILL required | **HIGH (S12)** |
| Power failure | none | none | **no autostart — kiosk stays down** | Medium |

---

## 27. Timing Analysis

### Verified constants (**CONFIRMED from source**)

| Stage | Timeout | Retries | Blocking? |
|---|---|---|---|
| `READY` handshake (SHOOT3) | 15.0 s | — | yes |
| Self-test reply | 5.0 s | — | yes |
| `STATUS?`/`CSTATUS?`/`PSTATUSC?`/`HSTATUSn?` reply | 3.0 s | — | yes |
| Serial watchdog ping | 5.0 s interval / 3.0 s reply, 2 misses → E-stop | — | background |
| Homing command (`homeN`/`gohomeN`) | **30 s** | 2 (manual-stop only) | yes |
| Shoot per axis | **60 s** | 0 | yes |
| Person detection hold | **5 s continuous** (no overall cap) | — | yes, **unbounded** |
| Chest align — no-person | 5.0 s | — | yes |
| Chest align — **overall** | **NONE** | — | yes, **unbounded** |
| Eye align — overall | **NONE** | — | yes, **unbounded** |
| Face recognition budget | **7 s** | — | yes |
| Post-align display | 3 s (chest) / 4 s (eye) | — | yes |
| Serial write | 1.0 s | — | — |
| Min gap between writes | 25 ms | — | — |
| DTR settle | 0.6 s + 0.25 s (SHOOT3); 0.5 + 0.2 (EYE4) | — | — |

### Measured durations — Architecture A only (**CONFIRMED by live run**)

| Stage | Measured |
|---|---|
| Server boot → healthy | **1 s** (models preloaded at import) |
| App launch → first identify | ~5 s |
| Identify (match) | **0.4 s** after first frame |
| MATCHED overlay | 0.43 s after match |
| Camera release | **225 ms** |
| Calibration stages (stubs) | **0.6 s total** |
| 1-min video + camera stages | ~2.5 min |
| Acquisition (4 parallel captures) | **~4.7 min** (10:12:20 → 10:16:58) |
| Playback + report generation | ~3 min |
| PDF written | 10:17:10 (during playback) |
| Report published | 10:20:06 |
| **Total session** | **10 min 38 s** |

### Architecture B durations: **UNKNOWN — requires runtime measurement**

Homing, shooting, and alignment convergence times cannot be derived from source (they depend on firmware speeds, travel distances, and how fast a visitor settles). Only their *timeouts* are known. The field logs give one data point: an `11.5 min` instrumented `meditation-app 1.0` run producing a 19 MB report (`docs/hardware-team-bugs.md`).

---

## 28. Current System Reality Check — What the system REALLY does today

### Confirmed working

- **Architecture A end-to-end**, verified by execution: identify → match → pipeline → 1-min video → 4-camera stages → 5-min capture → playback → PDF → in-app render → reset for next visitor. Ran twice consecutively with two different visitors.
- `am-mock-server`: FastAPI on :8000, 16 enrolled faces, sface/128-dim, L2 ≤ 0.8.
- Face recognition on real hardware: `VISHNUKUMAR` @ 0.69, `teja v` @ 0.687.
- All four capture streams on real devices (C920, Arducam, RealSense D435, USB thermal cam).
- Report generation and atomic publication.
- The Arduino protocol, homing, shoot, radar, and alignment code in `latest_A` is **real, complete, and has demonstrably run** — the field logs prove it (including real failures).

### Partially implemented

- Architecture B's error handling: excellent at the *hardware* layer, absent at the *liveness* layer (no radar timeout, no alignment timeout).
- Camera-failure handling: frame-grab checks exist; no watchdog for a camera that stalls without erroring.
- Arduino reconnection: only `CHEST4.py` reconnects; `HOME4`/`SHOOT3` abort.

### Stubbed / simulated

- **`mark1/HOME1.py`, `SHOOT1.py`, `CHEST1.py`, `EYE1.py`** — print a line, exit 0. This is the entirety of Architecture A's "calibration".

### Dead / unused code

- `latest_A/face_client/prev_pipeline.py` — rollback snapshot, not imported.
- `emergency_stop_img1.png` — referenced nowhere.
- `latest_A/person_detail.txt` (`eshwar@1`) — stale; the orchestrator reads a different path.
- `Diya-main/docs/archive/` — the retired Node/Express + Postgres QR/phone flow.
- `am-mock-server/scripts/smoke_test.sh` — still assumes the abandoned Podman flow.
- `DIYA_IDENTIFY_SERVER_URL` — set by C#, never read by the client.

### Blocked — why Architecture B cannot run here (**5 hard blockers, all CONFIRMED**)

| # | Blocker | Evidence |
|---|---|---|
| 1 | **No Arduino** | no `/dev/ttyACM*`; no VID `2341` on USB |
| 2 | **No LD2410 radar** | no `/dev/serial/by-id`; no VID `10c4` (CP2102) on USB |
| 3 | **No `python3.10`** | `kiosk_run.sh` hardcodes `python3.10 -u`; machine has 3.12.9 / 3.13.14 / 3.14.6 only |
| 4 | **Missing deps** | `mediapipe`, `cvzone`, `pyserial` all absent from `python3` (only `cv2` present) |
| 5 | **Missing client checkout** | `~/Desktop/am-mock-client-1.1.0` does not exist |

`meditation-app` **does** exist at `/usr/local/bin/meditation-app`, and `v4l2-ctl` (needed by `camera_utils.py`) is installed. So blockers 1–5 are the complete list.

The field logs reference `/home/bharataap/.local/lib/python3.10/site-packages/cv2` — meaning python3.10 **did** exist on the machine where these logs were produced. **INFERRED:** `latest_A` was developed and run on a different machine (or before a Python upgrade), and this checkout has not been re-provisioned.

### Unknown

- What "shoot" physically actuates.
- Arduino firmware behaviour: PID gains, step size, travel limits, halt latency.
- Whether `camera.device: 3` is correct on the real kiosk rig.
- Real-world reliability of the 5-consecutive-match streak within 7 s.
- Convergence time for chest/eye alignment.

---

## 29. Known Limitations

1. Architecture A performs **no physical alignment** — the visitor is captured wherever they happen to sit.
2. Architecture B provides **no visitor-facing UI** — raw OpenCV windows, no report display.
3. Neither architecture reads the other's work; integrating them is unstarted work.
4. `run1.sh`'s default `mark1` path is wrong on this machine.
5. Report email/SMS delivery is a confirmed-but-deferred requirement; the identify response already carries an unpopulated `email` field.
6. No inactivity auto-reset in either architecture.
7. `aurar100.onnx` absent → AuraFace path unusable.
8. Deployment docs describe a systemd autostart that is not installed.
9. Architecture B re-implements the Arduino protocol five times.
10. `latest_A` has a single squashed commit — no development history to bisect.

---

## 30. Technical Risks

| Risk | Impact | Likelihood |
|---|---|---|
| **S1** unbounded alignment loop with a person in the rig | **injury / mechanism damage** | Medium |
| **S8** Arduino firmware unreviewable and unversioned here | all motion limits unauditable | Certain |
| **S12** children survive SIGTERM holding cameras | next visitor's session fails | **Observed** |
| **S3** `Ctrl+C` → exit 0 → pipeline advances | actuator fires after an abort | Medium |
| **S2** radar waits forever | silent kiosk hang | Medium |
| **S4** stale `person_detail.txt` | wrong visitor's session | Low–Medium |
| **S6** uncapped restart re-fires actuators | mechanical wear, visitor confusion | Medium |
| Two architectures diverging further | integration cost grows | High |
| No autostart | kiosk stays down after power loss | Certain |

---

## 31. Recommended Improvements

*(Recommendations only — nothing was modified, per instruction §25.)*

**Safety first, in priority order:**

1. **Add an overall alignment timeout + attempt cap to `CHEST4.py`/`EYE4.py`** (S1). Mirror the pattern already used for homing: on expiry, send `E:0`/`F:0`, shut down cleanly, and return non-zero. This is the single highest-value change.
2. **Change `emergency_stop`'s default `exit_code` to non-zero** (S3), so an aborted run can never be read as success.
3. **Add a timeout to `trigger_y.py`** (S2) with a distinct exit code for "nobody sat down" versus a hardware fault.
4. **Clear `person_detail.txt` immediately before invoking the camera step** (S4) — one line, closes the stale-data hole entirely.
5. **Use process-group kill + traps** so children cannot survive and hold cameras (S12); the fix is already recommended in `docs/hardware-team-bugs.md`.
6. **Vendor the Arduino firmware into this repository** (S8) so motion limits are reviewable and versioned alongside the Python that drives them.
7. **Add `flock` to `kiosk_run.sh`** (S5) and a retry cap to the outer loop (S6).

**Operational:**

8. Replace the hardcoded `python3.10` with a configurable interpreter, and provision `mediapipe`/`cvzone`/`pyserial`.
9. Replace the two "EDIT THIS" placeholders with environment variables.
10. Extract the duplicated Arduino handshake/watchdog into a shared module.
11. Make `client.py` honour `DIYA_IDENTIFY_SERVER_URL`, or stop setting it.
12. Fix the `feh` leak (S10) and `acquisition`'s always-zero exit (S11).
13. Install the systemd user unit if unattended operation is intended.

**Strategic — the decision that unblocks everything else:** decide whether the kiosk's future is A (C# shell) or B (bash pipeline). The natural merge is to keep Architecture A's UI, packaging, and report display, and replace the `mark1` stubs with `latest_A`'s real stages — `run1.sh` already has the correct call sites and retry semantics for exactly this.

---

## 32. Plain-English Explanation

*(Analogy — clearly labelled as such.)*

> `kiosk_run.sh` is the **conductor**. The Python scripts are **section leads**: one parks the machine at a known starting position, one deploys the equipment, one waits for the audience member to sit, and two aim the instruments. The **Arduino is the stagehand** — it holds the actual levers, and the Python scripts only shout instructions to it and listen for confirmations. The **radar is the doorman** — it will not let the show start until someone is genuinely seated. The **cameras are the eyes**, and face recognition is the **ticket check**. The meditation app is the **performance itself**.

Concretely, in order: park the rig at zero → deploy the sensors → wait until someone actually sits down → tilt the chest camera until the torso is centred → tilt the eye camera until the eyes are centred → check who this is → play the meditation and print their report.

The catch: **the conductor has two orchestras.** One (`Diya-main`) has a beautiful concert hall, a printed programme, and mimes the tuning. The other (`latest_A`) has real instruments that genuinely play but no venue. They have never performed together.

---

## 33. Glossary

| Term | Meaning |
|---|---|
| **M1 / M2** | chest axis / eye axis motors |
| **Homing** | driving an axis to a known mechanical reference so later moves have an origin |
| **Prox** | proximity sensor; early, contactless warning before a mechanical limit switch |
| **A0** | analog pin 0 — the early-warning collision prox |
| **NO/NC** | normally-open / normally-closed switch contacts, paired so wiring faults are detectable |
| **`E:` / `F:`** | serial commands carrying the chest / eye pixel-error term to the firmware |
| **Dead-band** | ±8 px window inside which alignment is "good enough" and motion stops |
| **YuNet** | OpenCV's native face **detector** (bbox + 5 landmarks) |
| **SFace** | OpenCV's native face **embedder**, 128-dim |
| **AuraFace R100** | alternate ArcFace-style embedder, 512-dim (model file absent) |
| **Normalised L2** | the server's distance metric; ≤ 0.8 counts as a match |
| **Landmark 168** | MediaPipe FaceMesh point between the eyes (glabella) |
| **LD2410** | mmWave radar presence sensor |
| **Gate** | LD2410 range bucket, 750 mm each, 9 total (~6.75 m) |
| **`flock`** | advisory file lock enforcing single-instance |
| **FlashCap** | the C# V4L2 capture library |
| **`PIPESTATUS[0]`** | bash array giving the first pipeline command's exit code, not `tee`'s |

---

## 34. Answers to the 25 Questions

1. **What starts the system?** Nothing automatic — no systemd, autostart, or cron. Manual launch only. **CONFIRMED.**
2. **True main orchestrator?** Two, unconnected: `PipelineRunner`→`run1.sh` (A), `kiosk_run.sh` (B). Only A runs here.
3. **`HOME4.py`?** Homes M1 and M2 to their limit switches after a switch self-test and collision gate, under a serial watchdog. Exit 2 on hardware fault.
4. **`SHOOT3.py`?** After `SELFTEST:PASS` and `PROXC:CLEAR`, fires `shoot m1` then `shoot m2`, each with a 60 s timeout. What is physically actuated is **UNKNOWN**.
5. **`trigger_y.py`?** LD2410 radar gate — requires 5 continuous seconds in the 650–1050 mm band plus a motion blip. **Waits forever otherwise.**
6. **`CHEST4.py`?** MediaPipe Pose → torso centre from landmarks 11/12/23/24 → streams `E:<err>` at ~30 Hz until |err| ≤ 8 px → saves `Alined_CHEST_.jpg`.
7. **`EYE4.py`?** cvzone FaceMesh → landmark 168 → streams `F:<err>` until |err| ≤ 8 px → saves `Alined_EYE_.jpg`.
8. **`client.py`?** YuNet + SFace 128-dim; POSTs the vector to `/api/v1/identify/`. In A it reads frames from stdin; in B it owns the camera and writes `person_detail.txt`.
9. **Arduino ↔ Python?** USB serial 115200, ASCII line protocol, main thread writes / daemon thread parses, 25 ms write floor, 5 s watchdog.
10. **M1/M2 control?** `home1/2`, `gohome1/2`, `shoot m1/m2`, and continuous `E:`/`F:` error terms. **Python sends error only — the PID lives in firmware not in this repo.**
11. **LD2410's effect?** Hard gate between the actuator stage and alignment; blocks until a person is confirmed seated.
12. **Chest math?** `y3=(lm11+lm12)/2`, `y6=(lm23+lm24)/2`, `y7=(y3+y6)/2`, `error = h/2 − y7`.
13. **Eye math?** `error = h/2 − face[168].y`.
14. **Recognition confirmed how?** 5 **consecutive** same-name identifications within 7 s. The doc's example (Vishnu, Vishnu, Unknown, Vishnu, Vishnu) is **REJECTED** — `Unknown` resets the streak to 0.
15. **`person_detail.txt`?** Overwritten once per camera run with a name or `error-person`; read by `kiosk_run.sh` to branch. No freshness guarantee (S4).
16. **After success?** B launches `meditation-app`. A shows MATCHED, releases the camera, runs the pipeline, then renders the PDF in-app.
17. **After failure?** B restarts the **entire** sequence from `HOME4.py`, uncapped. A gives up after 45 unmatched frames and offers manual name/email entry.
18. **Hardware failure?** Fullscreen fault screen, `STOP` to the Arduino, non-zero exit, run aborts. No auto-recovery — an operator is required.
19. **Where does `Diya-main` fit?** The visitor-facing kiosk shell, packaging, and report display — with **stubbed** calibration.
20. **Where does `latest_A` fit?** The real hardware control layer plus a forked FR client — with **no** UI or report display.
21. **Are they connected?** **No.** Zero code references either way; only one comment in `HOME4.py:24` mentioning `run1.sh`. `kiosk_run.sh` points at a third checkout that doesn't exist here.
22. **Which controls the hardware?** **Neither today.** A runs but its calibration is stubs; B has the real control but is blocked by 5 missing prerequisites.
23. **Which parts are stubs?** `mark1/HOME1|SHOOT1|CHEST1|EYE1.py` — the whole of A's calibration.
24. **Biggest safety risks?** S1 unbounded alignment loop; S8 unreviewable firmware; S12 children surviving SIGTERM holding cameras; S3 `Ctrl+C` exiting 0.
25. **Fix before production?** In order: alignment timeout (S1), non-zero E-stop exit code (S3), radar timeout (S2), clear `person_detail.txt` before use (S4), process-group cleanup (S12), vendor the firmware (S8), `flock` + retry cap (S5/S6). Then decide A-vs-B and merge.

---

## 35. Final Conclusion

The Diya Meditation Kiosk is **two half-systems**. Architecture A is a polished, packaged, visitor-ready kiosk whose hardware calibration is four `print()` statements. Architecture B is a careful, safety-conscious hardware control layer — provable limit switches, dead-prox detection, serial watchdogs, layered collision gates — with no visitor-facing shell and no ability to run on this machine.

The engineering quality in `latest_A`'s hardware layer is genuinely high; the failure-detection design around unprovable proximity sensors is the work of someone who has thought hard about how this rig breaks. That makes the two unbounded loops (alignment, radar) conspicuous by contrast: **every other motion path in the system is bounded by an explicit timeout, and the one stage that moves a motor with a person deliberately positioned inside the mechanism is not.**

Nothing in this investigation was modified. Verification of Architecture A was performed by executing it end-to-end; Architecture B was verified by source inspection only, because the Arduino, the radar, `python3.10`, three Python packages, and the referenced client checkout are all absent from this machine.
