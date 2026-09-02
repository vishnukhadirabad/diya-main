#!/usr/bin/env bash
# skip_calib.sh — TEMPORARY stand-in for run_calib.sh while the Arduino and
# LD2410 radar are not connected. Skips all five latest_A hardware stages and
# reports success so the kiosk proceeds straight to face recognition.
#
# Use by launching the kiosk with:
#   DIYA_CALIB_SCRIPT=<this file>
# Remove that env var once the hardware is connected to restore real calibration.
echo "[calib] SKIPPED — Arduino/LD2410 not connected; proceeding without hardware alignment."
exit 0
