#!/bin/bash
# This script runs the check_similarity.py script

# Navigate to the directory where the Python script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit
# Run the Python script
python3 visual_test4.py
