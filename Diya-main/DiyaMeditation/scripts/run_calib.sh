#!/usr/bin/env bash
# =============================================================================
# run_calib.sh — hardware calibration, runs BEFORE face recognition.
#
# Stages (latest_A, real Arduino/radar hardware):
#   HOME4.py    — home both axes (M1 chest, M2 eyes) after a switch self-test
#   SHOOT3.py   — fire the actuators (shoot m1, shoot m2)
#   trigger_y.py— LD2410 radar: block until a person is seated (850±200mm, 5s)
#   CHEST4.py   — MediaPipe Pose: servo M1 until the torso is centred (±8px)
#   EYE4.py     — FaceMesh: servo M2 until the eyes are centred (±8px)
#
# Called by the Diya kiosk (PipelineRunner.RunCalibrationAsync) at the start of
# every visitor session; only after this exits 0 does the kiosk open the C920
# and run face recognition. EYE4 uses that same C920, which is why this must
# fully finish first.
#
# Failure semantics (mirrors latest_A/kiosk_run.sh): ANY stage exiting non-zero
# is FATAL — exit with that code. Exit 2 = hardware fault (limit switch /
# homing / prox) and needs an operator, not a retry loop.
# =============================================================================

set -euo pipefail

CALIB_LOCK="${DIYA_CALIB_LOCK:-/tmp/diya-calib.lock}"
exec 9>"$CALIB_LOCK"
if ! flock -n 9; then
    echo "[calib] ERROR: a calibration is already running ($CALIB_LOCK)." >&2
    exit 1
fi

WORK_DIR="${DIYA_PIPELINE_WORK_DIR:-$HOME/Desktop/diya /latest_A}"
# mediapipe/cvzone/pyserial live in the python3.12 venv inside latest_A
# (mediapipe has no 3.13 wheels).
PYTHON="${DIYA_PIPELINE_PYTHON:-$WORK_DIR/.venv312/bin/python}"

STEPS=(
    "HOME4.py"
    "SHOOT3.py"
    "trigger_y.py"
    "CHEST4.py"
    "EYE4.py"
)

RED='\033[0;31m'; GRN='\033[0;32m'; BLU='\033[0;34m'; NC='\033[0m'
log_info() { echo -e "${BLU}[INFO ]${NC}  $*"; }
log_ok()   { echo -e "${GRN}[OK   ]${NC}  $*"; }
log_err()  { echo -e "${RED}[FAIL ]${NC}  $*"; }

# ── sanity checks ────────────────────────────────────────────────────────────
if [[ ! -d "$WORK_DIR" ]]; then
    log_err "Calibration work directory not found: $WORK_DIR"
    exit 1
fi
for script in "${STEPS[@]}"; do
    if [[ ! -f "$WORK_DIR/$script" ]]; then
        log_err "Missing stage script: $WORK_DIR/$script"
        exit 1
    fi
done
if [[ ! -x "$PYTHON" ]]; then
    log_err "Calibration python not found: $PYTHON"
    log_err "Create it with: python3.12 -m venv \"$WORK_DIR/.venv312\" && pip install pyserial mediapipe cvzone opencv-python"
    exit 1
fi

# ── stages ───────────────────────────────────────────────────────────────────
# -u so Arduino FAULT:/ERROR:/DONE: lines relayed by the scripts appear live.
for script in "${STEPS[@]}"; do
    log_info "Running $script ..."
    if (cd "$WORK_DIR" && "$PYTHON" -u "$script"); then
        log_ok "$script succeeded."
    else
        code=$?
        log_err "$script exited with code $code — aborting calibration."
        if [[ "$code" -eq 2 ]]; then
            log_err "Exit 2 = HARDWARE FAULT (limit switch / homing / prox). Operator attention required."
        elif [[ "$code" -eq 1 && "$script" == "HOME4.py" ]]; then
            log_err "Likely cause: Arduino not connected (no /dev/ttyACM*)."
        fi
        exit "$code"
    fi
done

log_ok "Calibration complete — rig aligned, cameras released."
exit 0
