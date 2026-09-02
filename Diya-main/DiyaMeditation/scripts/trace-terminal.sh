#!/usr/bin/env bash
# =============================================================================
# trace-terminal.sh
# Find out WHICH process spawns the stray terminal window that appears when the
# pipeline reaches STEP 5 (meditation-app).  See docs/responsibilities.md §5.
#
# RUNBOOK
#   Terminal A:  sudo ./trace-terminal.sh
#   Terminal B:  run the kiosk normally (or just: meditation-app) and reproduce
#                the stray window.
#   Terminal A:  Ctrl-C  →  prints the verdict, keeps the logs.
#
# Logs are left in /tmp/diya-trace-<timestamp>/ so a run can be re-analysed.
#
# WHY NOT JUST `execsnoop-bpfcc | grep -iE "terminal|xterm|konsole"`:
#   1. Ubuntu 24.04+ ships **ptyxis** as the default terminal (gnome-terminal,
#      xterm and konsole are often not installed at all) — that pattern matches
#      none of it.
#   2. ptyxis/kgx are single-instance GApplications: if one is already running,
#      a new WINDOW is requested over D-Bus and NO execve happens.  execsnoop is
#      blind to that by construction.
#   3. execsnoop-bpfcc is a Python tool; on a pipe it block-buffers, so hits can
#      arrive long after the run is over.
#
#   So this script runs three independent detectors:
#     (1) execsnoop  — every exec, unfiltered, to a file
#     (2) new /dev/pts allocations — display-server agnostic; catches a terminal
#         window even when no new process is exec'd (the D-Bus case)
#     (3) window list — X11/XWayland, best effort
# =============================================================================

set -uo pipefail

# ── colours (match run1.sh) ──────────────────────────────────────────────────
RED='\033[0;31m'
GRN='\033[0;32m'
YLW='\033[1;33m'
BLU='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLU}[INFO ]${NC}  $*"; }
log_ok()   { echo -e "${GRN}[OK   ]${NC}  $*"; }
log_warn() { echo -e "${YLW}[WARN ]${NC}  $*"; }
log_err()  { echo -e "${RED}[FAIL ]${NC}  $*"; }

# Every terminal emulator we can think of, not just the three in the original
# command. `kgx` is GNOME Console; `ptyxis` is the Ubuntu 24.04+ default.
TERM_RE='terminal|xterm|konsole|ptyxis|kgx|gnome-console|tilix|alacritty|kitty|foot|terminator|urxvt|rxvt|guake|yakuake|lxterminal|xfce4-terminal|mate-terminal|deepin-terminal|qterminal|sakura|roxterm|wezterm|hyper|contour'

# ── preflight ────────────────────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
    log_err "Must run as root (execsnoop needs BPF). Try:  sudo $0"
    exit 1
fi

if ! command -v execsnoop-bpfcc &>/dev/null; then
    log_warn "execsnoop-bpfcc not found — installing bpfcc-tools ..."
    apt-get install -y bpfcc-tools || {
        log_err "Install failed. Run: sudo apt install bpfcc-tools"
        exit 1
    }
fi

OUT_DIR="/tmp/diya-trace-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$OUT_DIR"
EXEC_LOG="$OUT_DIR/execsnoop.log"
PTS_LOG="$OUT_DIR/pts.log"
WIN_LOG="$OUT_DIR/windows.log"

# The GUI belongs to the invoking user, not root.
GUI_USER="${SUDO_USER:-$(logname 2>/dev/null || echo root)}"
GUI_UID="$(id -u "$GUI_USER" 2>/dev/null || echo 0)"

PIDS=()
cleanup() {
    echo
    log_info "Stopping detectors ..."
    for p in "${PIDS[@]}"; do kill "$p" 2>/dev/null; done
    wait 2>/dev/null
    verdict
}
trap cleanup INT TERM

# ── detector 1: every exec, unfiltered ───────────────────────────────────────
# -x also records FAILED execs: a terminal that fails to launch still names the
# process that tried. stdbuf -oL defeats Python's block buffering.
log_info "Detector 1: execsnoop  → $EXEC_LOG"
stdbuf -oL execsnoop-bpfcc -x >"$EXEC_LOG" 2>&1 &
PIDS+=($!)

# ── detector 2: new pty allocations ──────────────────────────────────────────
# A terminal emulator opening a window allocates a new /dev/pts/N and runs a
# shell on it. Works under X11 AND Wayland, and catches the single-instance
# D-Bus case where detector 1 sees nothing.
log_info "Detector 2: /dev/pts watch  → $PTS_LOG"
(
    prev="$(ls /dev/pts 2>/dev/null | grep -E '^[0-9]+$' | sort -n | tr '\n' ' ')"
    while :; do
        cur="$(ls /dev/pts 2>/dev/null | grep -E '^[0-9]+$' | sort -n | tr '\n' ' ')"
        for n in $cur; do
            case " $prev " in
                *" $n "*) ;;
                *)
                    echo "=== $(date +%H:%M:%S) NEW PTY /dev/pts/$n ==="
                    # Who is on it, and who is their parent?
                    ps -eo pid,ppid,tty,user,comm,args \
                        | awk -v t="pts/$n" 'NR==1 || $3==t'
                    for pid in $(ps -eo pid,tty --no-headers \
                                 | awk -v t="pts/$n" '$2==t {print $1}'); do
                        ppid=$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ')
                        [[ -n "$ppid" ]] && {
                            echo "  ↳ parent of $pid:"
                            ps -o pid,ppid,user,comm,args --no-headers -p "$ppid" 2>/dev/null \
                                | sed 's/^/     /'
                        }
                    done
                    echo
                    ;;
            esac
        done
        prev="$cur"
        sleep 0.25
    done
) >"$PTS_LOG" 2>&1 &
PIDS+=($!)

# ── detector 3: window list (best effort) ────────────────────────────────────
if command -v wmctrl &>/dev/null; then
    log_info "Detector 3: window list  → $WIN_LOG"
    (
        while :; do
            sudo -u "$GUI_USER" \
                env DISPLAY="${DISPLAY:-:0}" \
                    XAUTHORITY="/run/user/$GUI_UID/gdm/Xauthority" \
                wmctrl -lp 2>/dev/null \
              | while read -r _id _desk wpid _host wtitle; do
                    printf '%s\t%s\t%s\n' \
                        "$wpid" "$(ps -o comm= -p "$wpid" 2>/dev/null)" "$wtitle"
                done
            sleep 1
        done | sort -u
    ) >"$WIN_LOG" 2>&1 &
    PIDS+=($!)
else
    log_warn "Detector 3 skipped: wmctrl not installed (sudo apt install wmctrl)."
    log_warn "Detectors 1 and 2 are the important ones — continuing."
    echo "(wmctrl not installed)" >"$WIN_LOG"
fi

# ── wait ─────────────────────────────────────────────────────────────────────
echo
log_ok "Tracing. Now reproduce the stray terminal window in another terminal:"
echo "         meditation-app          # or run the kiosk end-to-end"
echo
log_info "Press Ctrl-C here once you have seen the window."
echo

# ── verdict ──────────────────────────────────────────────────────────────────
verdict() {
    echo
    echo "═══════════════════════════════════════════════════════════════════"
    echo " VERDICT"
    echo "═══════════════════════════════════════════════════════════════════"

    echo
    log_info "[1] Terminal-emulator execs (PCOMM PID PPID RET ARGS):"
    if grep -iE "$TERM_RE" "$EXEC_LOG" 2>/dev/null | grep -v "trace-terminal"; then
        echo
        log_info "    → parents of those execs (this is the culprit):"
        # Column 3 is PPID. Resolve it against the log itself, so it works even
        # after the parent has exited.
        grep -iE "$TERM_RE" "$EXEC_LOG" 2>/dev/null \
          | grep -v "trace-terminal" \
          | awk '{print $3}' | sort -u \
          | while read -r ppid; do
                [[ -z "$ppid" || "$ppid" == "PPID" ]] && continue
                echo "    PPID $ppid:"
                live=$(ps -o pid,ppid,user,comm,args --no-headers -p "$ppid" 2>/dev/null)
                if [[ -n "$live" ]]; then
                    echo "$live" | sed 's/^/      [live] /'
                else
                    awk -v p="$ppid" '$2==p {print "      [from log] " $0}' "$EXEC_LOG" | head -3
                fi
            done
    else
        log_warn "    No terminal-emulator exec seen."
        log_warn "    That does NOT mean none appeared — see [2]."
    fi

    echo
    log_info "[2] New pty allocations (a terminal WINDOW opened, exec or not):"
    if [[ -s "$PTS_LOG" ]]; then
        cat "$PTS_LOG"
    else
        log_ok "    None — no terminal window opened a pty during the trace."
    fi

    echo
    log_info "[3] Windows seen (X11/XWayland only):"
    grep -iE "$TERM_RE" "$WIN_LOG" 2>/dev/null || echo "    (no terminal-like window titles)"

    echo
    log_info "[4] What meditation-app actually ran (for context):"
    grep -iE "mpv|feh|ffplay|frontback1|acquisition|output_analysis|Front|t3\b" \
        "$EXEC_LOG" 2>/dev/null | head -40 || echo "    (nothing)"

    echo
    echo "═══════════════════════════════════════════════════════════════════"
    log_ok "Full logs kept in: $OUT_DIR"
    echo "  execsnoop.log  — every exec during the run (unfiltered)"
    echo "  pts.log        — new terminal ptys + their parent process"
    echo "  windows.log    — window list samples"
    echo "═══════════════════════════════════════════════════════════════════"
    exit 0
}

# Sleep until interrupted.
while :; do sleep 1; done
