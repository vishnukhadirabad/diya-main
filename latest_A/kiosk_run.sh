#!/bin/bash
# kiosk_run.sh — runs the full kiosk sequence:
#   HOME4 -> SHOOT3 -> trigger_y -> CHEST4 -> EYE4 -> face-recognition camera -> meditation-app
#
# Face-recognition step behaviour:
#   - Runs .venv/bin/python client.py --camera in the camera-client project dir.
#   - Reads person_detail.txt afterward:
#       * a real name  -> success, proceed to meditation-app
#       * "error-person" (or the file is missing) -> logs the failure and
#         restarts the ENTIRE sequence from HOME4.py
#
# Logs everything to log_file_check, and on any step failure (a script exit
# code != 0, OR a failed/no-match face detection) also logs to log_file_failure.
#
# TERMINATE ANYTIME WITH: Ctrl+C
#
# Usage:
#   chmod +x kiosk_run.sh
#   ./kiosk_run.sh

# Resolve this script's own directory so log files always land in a fixed
# place regardless of which directory we `cd` into for the camera step.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_CHECK="$SCRIPT_DIR/log_file_check"
LOG_FAILURE="$SCRIPT_DIR/log_file_failure"

STEPS=(
    "HOME4.py"
    "SHOOT3.py"
    "trigger_y.py"
    "CHEST4.py"
    "EYE4.py"
)

# ---- Camera / face-recognition client ----
# EDIT THIS to the actual path of your am-mock-client-1.1.0 project.
CAMERA_CLIENT_DIR="$HOME/Desktop/am-mock-client-1.1.0"
CAMERA_CLIENT_PYTHON="$CAMERA_CLIENT_DIR/.venv/bin/python"
PERSON_DETAIL_FILE="$CAMERA_CLIENT_DIR/person_detail.txt"

# ---- Meditation app ----
# EDIT THIS to whatever actually launches the meditation app on this kiosk
# (a binary on PATH, a full path to a script, etc).
MEDITATION_APP_CMD="meditation-app"

TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S')"
CURRENT_STEP=""

# ---- ADD: automatic log cleanup every N invocations ----
# Each run of this script is a separate process, so "every 10 runs" needs a
# persistent counter on disk -- .kiosk_run_count, right next to the logs.
# CLEAN_EVERY_N_RUNS controls the cadence; change it here if you want a
# different interval.
COUNTER_FILE="$SCRIPT_DIR/.kiosk_run_count"
CLEAN_EVERY_N_RUNS=10

RUN_COUNT=1
if [ -f "$COUNTER_FILE" ]; then
    RUN_COUNT=$(( $(cat "$COUNTER_FILE" 2>/dev/null || echo 0) + 1 ))
fi
echo "$RUN_COUNT" > "$COUNTER_FILE"

# ---- ADD: rotation function, run via the EXIT trap below so it fires
# after every possible exit path (normal success, any of the "exit N"
# failure paths, and Ctrl+C -- since cleanup_on_interrupt's own "exit 130"
# still triggers this EXIT trap afterward). This guarantees the cleanup
# always runs exactly once at the very end of the invocation that hits the
# Nth run, regardless of how that particular run ended. ----
rotate_logs_if_needed() {
    if [ $(( RUN_COUNT % CLEAN_EVERY_N_RUNS )) -eq 0 ]; then
        : > "$LOG_CHECK"
        : > "$LOG_FAILURE"
        {
            echo "=================================================================="
            echo "LOG FILES ROTATED after run #$RUN_COUNT ($(date '+%Y-%m-%d %H:%M:%S'))"
            echo "Previous $CLEAN_EVERY_N_RUNS runs' history cleared."
            echo "=================================================================="
        } >> "$LOG_CHECK"
        echo "[kiosk_run.sh] Logs rotated after run #$RUN_COUNT."
    fi
}
trap rotate_logs_if_needed EXIT

# ---- Ctrl+C handling ----
# Ctrl+C sends SIGINT. Bash's default is to kill the whole foreground
# process group anyway, but trapping it here lets us log that the run
# was manually stopped (and where) instead of leaving log_file_check
# silent about why the run ended.
cleanup_on_interrupt() {
    local now
    now="$(date '+%Y-%m-%d %H:%M:%S')"
    {
        echo ""
        echo "=================================================================="
        echo "KIOSK RUN INTERRUPTED BY USER (Ctrl+C): $now"
        [ -n "$CURRENT_STEP" ] && echo "Was running   : $CURRENT_STEP"
        echo "=================================================================="
    } | tee -a "$LOG_CHECK" | tee -a "$LOG_FAILURE" > /dev/null
    exit 130
}
trap cleanup_on_interrupt SIGINT

{
    echo "=================================================================="
    echo "KIOSK RUN STARTED: $TIMESTAMP"
    echo "=================================================================="
} | tee -a "$LOG_CHECK"

RETRY_COUNT=0

# ---- ADD: outer loop so a no-match / error-person result can restart the
# whole sequence from HOME4.py, as opposed to the inner STEPS loop which is
# only for the fixed HOME4->EYE4 sequence run once per attempt. ----
while true; do
    RETRY_COUNT=$((RETRY_COUNT + 1))
    if [ "$RETRY_COUNT" -gt 1 ]; then
        {
            echo ""
            echo "=================================================================="
            echo "RESTARTING SEQUENCE FROM HOME4.py (attempt #$RETRY_COUNT): $(date '+%Y-%m-%d %H:%M:%S')"
            echo "=================================================================="
        } | tee -a "$LOG_CHECK"
    fi

    FAILED_STEP=""
    FAILED_EXIT_CODE=0

    # ---- Run the fixed HOME4 -> EYE4 sequence ----
    for script in "${STEPS[@]}"; do
        CURRENT_STEP="$script"
        echo "" | tee -a "$LOG_CHECK"
        echo "---- Running: $script ----" | tee -a "$LOG_CHECK"

        # -u = unbuffered, so log lines (and firmware FAULT:/ERROR:/DONE: lines
        # relayed by these scripts) show up in real time instead of in
        # delayed batches once the pipe buffer fills.
        python3.10 -u "$script" 2>&1 | tee -a "$LOG_CHECK"

        # PIPESTATUS[0] = python's real exit code, not tee's (tee itself
        # always exits 0, so "$?" alone would hide a failed script).
        EXIT_CODE=${PIPESTATUS[0]}

        if [ "$EXIT_CODE" -ne 0 ]; then
            FAILED_STEP="$script"
            FAILED_EXIT_CODE="$EXIT_CODE"
            break
        fi
    done

    if [ -n "$FAILED_STEP" ]; then
        {
            echo ""
            echo "=================================================================="
            echo "KIOSK RUN FAILED: $(date '+%Y-%m-%d %H:%M:%S')"
            echo "Failed at step : $FAILED_STEP"
            echo "Exit code      : $FAILED_EXIT_CODE"
            echo "=================================================================="
        } | tee -a "$LOG_CHECK" | tee -a "$LOG_FAILURE"
        exit "$FAILED_EXIT_CODE"
    fi

    # ---- Face-recognition camera step ----
    CURRENT_STEP="client.py --camera"
    echo "" | tee -a "$LOG_CHECK"
    echo "---- Running: client.py --camera ----" | tee -a "$LOG_CHECK"

    (cd "$CAMERA_CLIENT_DIR" && "$CAMERA_CLIENT_PYTHON" client.py --camera) 2>&1 | tee -a "$LOG_CHECK"
    CAMERA_EXIT_CODE=${PIPESTATUS[0]}

    if [ "$CAMERA_EXIT_CODE" -ne 0 ]; then
        # The client itself crashed/errored (not just "no face confirmed") --
        # treat this the same as any other fatal step failure, do NOT restart.
        {
            echo ""
            echo "=================================================================="
            echo "KIOSK RUN FAILED: $(date '+%Y-%m-%d %H:%M:%S')"
            echo "Failed at step : client.py --camera (crashed)"
            echo "Exit code      : $CAMERA_EXIT_CODE"
            echo "=================================================================="
        } | tee -a "$LOG_CHECK" | tee -a "$LOG_FAILURE"
        exit "$CAMERA_EXIT_CODE"
    fi

    # ---- Read the result client.py wrote to person_detail.txt ----
    if [ -f "$PERSON_DETAIL_FILE" ]; then
        PERSON_RESULT="$(head -n 1 "$PERSON_DETAIL_FILE" | tr -d '[:space:]')"
    else
        PERSON_RESULT=""
    fi

    if [ -z "$PERSON_RESULT" ] || [ "$PERSON_RESULT" = "error-person" ]; then
        {
            echo ""
            echo "=================================================================="
            echo "FACE NOT CONFIRMED: $(date '+%Y-%m-%d %H:%M:%S')"
            echo "person_detail.txt : ${PERSON_RESULT:-<missing/empty>}"
            echo "Action            : restarting sequence from HOME4.py"
            echo "=================================================================="
        } | tee -a "$LOG_CHECK" | tee -a "$LOG_FAILURE"
        # ---- back to the top of the outer while loop -> HOME4.py again ----
        continue
    fi

    # ---- Confirmed a person -- log it and fall through to meditation-app ----
    {
        echo ""
        echo "=================================================================="
        echo "PERSON CONFIRMED: $PERSON_RESULT  ($(date '+%Y-%m-%d %H:%M:%S'))"
        echo "=================================================================="
    } | tee -a "$LOG_CHECK"

    break
done

# ---- Meditation app ----
CURRENT_STEP="$MEDITATION_APP_CMD"
echo "" | tee -a "$LOG_CHECK"
echo "---- Running: $MEDITATION_APP_CMD ----" | tee -a "$LOG_CHECK"

$MEDITATION_APP_CMD 2>&1 | tee -a "$LOG_CHECK"
MEDITATION_EXIT_CODE=${PIPESTATUS[0]}

if [ "$MEDITATION_EXIT_CODE" -ne 0 ]; then
    {
        echo ""
        echo "=================================================================="
        echo "KIOSK RUN FAILED: $(date '+%Y-%m-%d %H:%M:%S')"
        echo "Failed at step : $MEDITATION_APP_CMD"
        echo "Exit code      : $MEDITATION_EXIT_CODE"
        echo "=================================================================="
    } | tee -a "$LOG_CHECK" | tee -a "$LOG_FAILURE"
    exit "$MEDITATION_EXIT_CODE"
fi

{
    echo ""
    echo "=================================================================="
    echo "KIOSK RUN COMPLETED SUCCESSFULLY: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "Person             : $PERSON_RESULT"
    echo "Sequence attempts  : $RETRY_COUNT"
    echo "Invocation #       : $RUN_COUNT (logs rotate every $CLEAN_EVERY_N_RUNS)"
    echo "=================================================================="
} | tee -a "$LOG_CHECK"
exit 0
