#!/usr/bin/env bash
# =============================================================================
# run1.sh — meditation session, runs AFTER face recognition.
#
# Integrated flow (latest_A → Diya-main → .deb):
#   1. run_calib.sh already homed/aligned the rig to the seated visitor
#      (latest_A stages) BEFORE face recognition ran.
#   2. The Diya kiosk identified the visitor (vendored client + mock server).
#   3. THIS script now runs the meditation stage: the packaged .deb at
#      /opt/meditation-app (frontback1) — NOT meditation_gui_updated, which is
#      deliberately unused in this flow.
#   4. The kiosk then renders the newest PDF from REPORT_DIR in-app.
# =============================================================================

set -euo pipefail

# ── single session ───────────────────────────────────────────────────────────
PIPELINE_LOCK="${DIYA_PIPELINE_LOCK:-/tmp/diya-pipeline.lock}"
exec 9>"$PIPELINE_LOCK"
if ! flock -n 9; then
    printf '\033[1;31m[run.sh] ERROR:\033[0m a session is already running (%s) — refusing to start a second.\n' \
        "$PIPELINE_LOCK" >&2
    exit 1
fi

# Meditation stage: the installed .deb.
MEDITATION_DIR="${DIYA_MEDITATION_DIR:-/opt/meditation-app}"
MEDITATION_ENTRY="${DIYA_MEDITATION_ENTRY:-frontback1}"

# Where the kiosk looks for the report (ReportRenderer.ReportDir). The .deb's
# frontback1 cd's into /opt/meditation-app/data before running t3, so the PDF
# normally lands in REPORT_DIR already; publish_report() is then a no-op and
# only acts if a future build writes the PDF elsewhere under MEDITATION_DIR.
REPORT_DIR="${DIYA_REPORT_DIR:-/opt/meditation-app/data}"

RED='\033[0;31m'; GRN='\033[0;32m'; BLU='\033[0;34m'; NC='\033[0m'
log_info() { echo -e "${BLU}[INFO ]${NC}  $*"; }
log_ok()   { echo -e "${GRN}[OK   ]${NC}  $*"; }
log_err()  { echo -e "${RED}[FAIL ]${NC}  $*"; }

publish_report() {
    local newest dest
    newest=$(ls -t "$MEDITATION_DIR"/*.pdf 2>/dev/null | head -1)
    [[ -z "$newest" ]] && return 0          # normal: t3 writes into REPORT_DIR
    dest="$REPORT_DIR/$(basename "$newest")"
    [[ "$newest" == "$dest" ]] && return 0
    if cp "$newest" "$dest.part" 2>/dev/null && mv "$dest.part" "$dest" 2>/dev/null; then
        log_ok "Report published to $dest"
    else
        rm -f "$dest.part" 2>/dev/null || true
        log_err "Could not copy the report to $REPORT_DIR."
        return 1
    fi
}

if [[ ! -x "$MEDITATION_DIR/$MEDITATION_ENTRY" ]]; then
    log_err "Meditation entrypoint not found or not executable:"
    log_err "  $MEDITATION_DIR/$MEDITATION_ENTRY"
    log_err "Install the meditation-app .deb, or set DIYA_MEDITATION_DIR."
    exit 1
fi

log_info "Launching $MEDITATION_ENTRY from $MEDITATION_DIR ..."
if (cd "$MEDITATION_DIR" && bash "./$MEDITATION_ENTRY"); then
    log_ok "$MEDITATION_ENTRY exited cleanly. Pipeline complete."
    publish_report || true
else
    log_err "$MEDITATION_ENTRY exited with an error."
    exit 1
fi
