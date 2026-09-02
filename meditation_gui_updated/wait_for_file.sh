#!/usr/bin/env bash
# Shared helper: block until a pipeline artefact shows up.
#
# The clip-generating stages (5M.py, morphing.py) now run in the background
# while playback is already on screen, so the consumer has to wait for each
# file instead of assuming it exists. Producers write to "<name>.part.<ext>"
# and rename on completion, so the file appearing at its final path means it is
# complete — no partial reads.
#
# The wait is bounded on purpose. morphing.py has a "no subject found" path
# where it exits without ever writing its output, and an unbounded wait there
# would hang the kiosk on a black screen with no way out.

# wait_for_file <path> [timeout_seconds]
#   Returns 0 once the file exists, 1 if it never turned up in time.
wait_for_file() {
    local path="$1"
    local timeout="${2:-180}"
    local waited_tenths=0
    local limit_tenths=$(( timeout * 10 ))

    while [[ ! -f "$path" ]]; do
        if (( waited_tenths >= limit_tenths )); then
            printf '[wait_for_file] gave up after %ss waiting for %s\n' \
                "$timeout" "$path" >&2
            return 1
        fi
        sleep 0.1
        (( waited_tenths += 1 ))
    done
    return 0
}
