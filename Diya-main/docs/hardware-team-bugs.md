# Bug list — `meditation-app` package (hardware team)

Findings from a full end-to-end trace of `meditation-app` on
`bharataap-MS-7D90` (Ubuntu 26.04, Wayland) on **2026-07-27**.

The session ran to completion: `frontback1` started 11:32:10, `t3` produced
`/opt/meditation-app/data/Complete_Report_Sub_2.pdf` (19 MB) at 11:43:28, and the
script exited with `All tasks completed successfully.` — a ~11.5 minute run.

Installed version under test: `meditation-app 1.0 amd64` (`dpkg -l`).
**Note:** we were told the current package is ~3.5 GB. The one installed here is
much smaller, so items below should be re-checked against the current build
before being actioned.

Everything marked **VERIFIED** was observed or reproduced directly. Items marked
**NEEDS INFO** are open questions for you.

---

## 1. `frontback1:37` — leaked fullscreen window when `t3` fails
**Severity: high — leaves an undismissable black screen on the kiosk**

`feh` is backgrounded at line 28 to hold a black screen during acquisition, and
its PID saved:

```bash
28:  feh -F "$DATA/black_background_1920x1080.png" &
29:  BLACK_PID=$!
```

Two of the three exit paths clean it up, but the `t3` failure path does not:

```bash
33:  [ $? -ne 0 ] && { kill $BLACK_PID 2>/dev/null; echo "acquisition failed."; exit 1; }   # kills it ✓
37:  [ $? -ne 0 ] && { echo "t3 failed."; exit 1; }                                          # LEAKS  ✗
40:  kill $BLACK_PID 2>/dev/null                                                             # kills it ✓
```

If `t3` fails, a fullscreen black `feh` window is orphaned and stays on screen
until someone kills it manually. On an unattended kiosk that is a dead machine.

**Fix:** add `kill $BLACK_PID 2>/dev/null;` to line 37, or better, use a single
`trap 'kill $BLACK_PID 2>/dev/null' EXIT INT TERM` right after line 29 and drop
the per-path kills.

---

## 2. `acquisition` always reports success — the failure check is dead code
**Severity: high — silent data loss, a broken session still produces a "report"**

`/opt/meditation-app/acquisition` ends with:

```bash
16:  bash "/opt/meditation-app/output_analysis"
17:  wait
18:  echo "Acquisition successfully executed"
```

The script's exit status is that of the final `echo`, which is **always 0**.
Confirmed by direct test: a script whose second-to-last command is `false` and
whose last command is that `echo` still exits `0`.

That makes the caller's guard unreachable:

```bash
frontback1:32-33:
  bash "$BASE_DIR/acquisition"
  [ $? -ne 0 ] && { kill $BLACK_PID; echo "acquisition failed."; exit 1; }   # never fires
```

So if `check_similarity4`, `visual_test6`, `depthacquisition`, `test2_time`, or
`morphing` fail, acquisition reports success, `t3` runs on missing or stale
inputs, and a report PDF is generated from bad data. The kiosk shows it to the
visitor as a real result.

**Fix:** capture and propagate the real status. `wait` on each background PID
individually and collect exit codes:

```bash
"$BIN/check_similarity4" & p1=$!
"$BIN/visual_test6"      & p2=$!
"$BIN/depthacquisition"  & p3=$!
"$BIN/test2_time"        & p4=$!
rc=0
for p in $p1 $p2 $p3 $p4; do wait "$p" || rc=1; done
[ $rc -ne 0 ] && exit 1
"$BIN/morphing" || exit 1
bash /opt/meditation-app/output_analysis || exit 1
echo "Acquisition successfully executed"
exit 0
```

---

## 3. Children survive the parent and keep holding the cameras
**Severity: high — a killed or crashed session locks the cameras for the next visitor**

**VERIFIED empirically.** We killed `frontback1` mid-run with `SIGTERM`. It died;
its descendants did not:

```
42934  bash /opt/meditation-app/acquisition
42936  /opt/meditation-app/bin/visual_test6
42937  /opt/meditation-app/bin/depthacquisition
42938  /opt/meditation-app/bin/test2_time
```

They kept running and kept `/dev/video*` open. Only `SIGKILL` cleared them.

This matters because the Diya kiosk must be able to abort a session (visitor
walks away, timeout, reset). Today an abort leaves camera-holding ghosts, and the
next visitor's session cannot open the cameras.

**Fix:** run the pipeline in its own process group and trap signals, e.g. in
`frontback1`:

```bash
trap 'kill -- -$$ 2>/dev/null' EXIT INT TERM
```

so terminating the script tears down the whole tree.

---

## 4. No cleanup handlers anywhere
**Severity: medium**

None of `frontback1`, `acquisition`, or `output_analysis` installs a `trap`. Any
interruption (Ctrl-C, systemd stop, kiosk reset) leaves whatever was running at
that moment — the `feh` black screen, a fullscreen `ffplay`, the acquisition
binaries — alive and on screen. Fixes 1 and 3 both fall out of adding traps.

---

## 5. Errors are actively discarded
**Severity: medium — failures are invisible in the logs**

```bash
output_analysis:7:   "$BIN/5M" 2>/dev/null || true    # discards stderr AND ignores exit code
output_analysis:19:  ffplay -t 50 -fs -autoexit "$video" 2>/dev/null
```

`5M` generates the composite output video. If it fails, nothing is recorded
anywhere and `output_analysis` continues as if it worked. Same for every
`ffplay`. When a session produces a bad report, there is no way to find out why
after the fact.

Also `output_analysis:8` — the bare `wait` on line 8 follows a *foreground*
command and is a no-op. Same for `acquisition:13` and `:17`.

**Fix:** drop `2>/dev/null`, let stderr reach the journal, and check exit codes.

---

## 6. `mpv` is the only step with no error check
**Severity: low**

Every other step in `frontback1` is guarded:

```bash
 9:  mpv --fs "$DATA/meditation_visualRohan/ONE_MINS.mp4"    # unchecked
12:  "$BIN/Front"
13:  [ $? -ne 0 ] && { echo "Front failed. Exiting."; exit 1; }
```

If the video is missing or the display is unavailable, the session proceeds
silently without the meditation visual the whole exercise depends on.

---

## 7. Three fullscreen windows fight the kiosk for the screen
**Severity: medium — this is our shared window-management problem**

The package maps fullscreen windows at three points:

```bash
frontback1:9       mpv --fs ...
frontback1:28      feh -F ...            (backgrounded)
output_analysis:19 ffplay -t 50 -fs ...  (up to 4 videos, 50s each)
```

The Diya kiosk is also fullscreen and does not currently yield. Whichever loses
the stacking race is what the operator perceives as a "stray window".

We are fixing our half (yield the screen before launching, reclaim after). What
we need from you: a statement of the **launch contract** — should
`meditation-app` own the display for the entire run, and should we minimise or
just lower our window?

---

## 8. The calibration scripts are not packaged at all
**Severity: high — blocks any deployment**

`HOME1.py`, `SHOOT1.py`, `CHEST1.py`, `EYE1.py` are not in `meditation-app` and
not in any `.deb`. They are expected at `$HOME/Desktop/mark1` (hardcoded in our
`scripts/run1.sh:15`, which we are parameterising). They do not exist on this
machine, so the full Diya pipeline cannot run here at all — we could only test
`meditation-app` by invoking it directly.

**Ask:** ship these in the `.deb` under a fixed path (e.g.
`/opt/meditation-app/calibration/`), or give us a tarball plus the exact Python
version and dependency list. They currently need `python3.10` specifically.

---

## 9. Stray terminal window — NOT reproducible here
**Severity: NEEDS INFO**

We could not reproduce it. Instrumented the full session with two independent
detectors (new-pty watch + process-table diff) across every step:

```
mpv → Front → splitSide → splitGaze → adjustment_test_updated
→ feh → acquisition (4 binaries) → morphing → output_analysis → 5M → ffplay ×2 → t3
```

**Result: zero new ptys, zero terminal processes, for the entire 11.5-minute run.**

Static analysis agrees: no terminal emulator is referenced in any
`/opt/meditation-app` script, a `strings` scan of all 12 binaries in `bin/` and
`depth_bin/` found none, and the package ships no `.desktop` file (`dpkg -L`).

So on this machine `meditation-app` does not open a terminal. The window is
likely coming from **how it is launched** on your machine. Please check:

1. Is there a `.desktop` file with `Terminal=true` — in `/usr/share/applications`,
   `~/.local/share/applications`, or `~/.config/autostart`?
2. Is the kiosk or `meditation-app` started from a wrapper script or an autostart
   entry that wraps it in a terminal?
3. Is the 3.5 GB build different from the `1.0` package we have here?

To identify it definitively on your machine, run our
`DiyaMeditation/scripts/trace-terminal.sh` as root and reproduce the window; it
prints the spawning process and its parent.

**Important:** the obvious command
`sudo execsnoop-bpfcc | grep -iE "terminal|xterm|konsole"` **returns nothing on
Ubuntu 24.04+ even when a terminal does open** — the default terminal is
`ptyxis`, which that pattern does not match, and single-instance GApplications
open a new window over D-Bus with no `execve` at all. Don't trust an empty result
from it.

---

## 10. Observation, not your bug: GPU not in use on this machine
**Severity: informational**

```
pci id for fd 7: 10de:2582, driver (null)
libEGL warning: egl: failed to create dri2 screen
GL version: 3.2 (OpenGL ES 3.2 Mesa 26.0.3), renderer: llvmpipe (LLVM 21.1.8)
```

MediaPipe fell back to CPU software rendering because this machine's NVIDIA
driver is not loaded. That is a local configuration problem, not a package
defect, but it explains the ~11.5 minute session length here and is worth knowing
when comparing timings. A note in your README about the expected GPU/driver
requirement would help.

---

## Confirmed working

For balance — these behaved correctly in the trace:

- Camera auto-detection picked the right device (`Front camera auto-detected at
  /dev/video10`, confirmed via `udevadm` to be the Arducam 8MP).
- All four acquisition binaries started and completed.
- `morphing` produced 1499 morphed frames and a valid output video.
- `t3` generated a well-formed 19 MB PDF.
- `feh` was correctly cleaned up on the success path.
