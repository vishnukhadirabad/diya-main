#!/usr/bin/env python3

import re
import subprocess

# =====================================================
# INPUT / OUTPUT FILES
# =====================================================

INPUT_FILE = "install_system_dependencies.sh"
OUTPUT_FILE = "system_requirements_versioned.txt"

# =====================================================
# EXTRACT PACKAGE NAMES
# =====================================================

packages = []

with open(INPUT_FILE, "r") as f:

    for line in f:

        line = line.strip()

        # Skip comments and empty lines
        if (
            not line
            or line.startswith("#")
            or line.startswith("sudo")
            or line.startswith("echo")
        ):
            continue

        # Remove trailing backslash
        line = line.replace("\\", "").strip()

        # Ignore apt keywords
        if line in ["apt", "install", "-y"]:
            continue

        # Detect package names
        if re.match(r'^[a-zA-Z0-9.+_-]+$', line):
            packages.append(line)

# =====================================================
# GET INSTALLED VERSIONS
# =====================================================

versioned_packages = []

missing_packages = []

for package in packages:

    try:

        result = subprocess.check_output(
            ["dpkg-query", "-W", "-f=${Version}", package],
            stderr=subprocess.DEVNULL
        )

        version = result.decode().strip()

        versioned_packages.append(
            f"{package}=={version}"
        )

    except subprocess.CalledProcessError:

        missing_packages.append(package)

# =====================================================
# WRITE OUTPUT FILE
# =====================================================

with open(OUTPUT_FILE, "w") as f:

    for item in sorted(versioned_packages):
        f.write(item + "\n")

# =====================================================
# DISPLAY RESULTS
# =====================================================

print("\n====================================")
print("System dependency versions extracted")
print("====================================")

print(f"\nOutput File: {OUTPUT_FILE}")

if missing_packages:

    print("\nPackages NOT installed locally:")
    print("--------------------------------")

    for pkg in missing_packages:
        print(pkg)

else:

    print("\nAll packages found successfully.")
