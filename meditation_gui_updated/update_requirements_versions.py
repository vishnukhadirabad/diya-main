#!/usr/bin/env python3

import pkg_resources
from pathlib import Path

# =====================================================
# FILE PATHS
# =====================================================

INPUT_REQUIREMENTS = "requirements.txt"
OUTPUT_REQUIREMENTS = "requirements_versioned.txt"

# =====================================================
# GET INSTALLED PACKAGES
# =====================================================

installed_packages = {
    pkg.key.lower(): pkg.version
    for pkg in pkg_resources.working_set
}

# =====================================================
# READ REQUIREMENTS
# =====================================================

requirements_path = Path(INPUT_REQUIREMENTS)

if not requirements_path.exists():
    print(f"ERROR: {INPUT_REQUIREMENTS} not found.")
    exit(1)

with open(INPUT_REQUIREMENTS, "r") as f:
    packages = [
        line.strip()
        for line in f
        if line.strip() and not line.startswith("#")
    ]

# =====================================================
# UPDATE WITH INSTALLED VERSIONS
# =====================================================

updated_requirements = []

missing_packages = []

for package in packages:

    package_name = package.split("==")[0].strip().lower()

    if package_name in installed_packages:

        version = installed_packages[package_name]

        updated_requirements.append(
            f"{package_name}=={version}"
        )

    else:

        missing_packages.append(package_name)

# =====================================================
# WRITE OUTPUT FILE
# =====================================================

with open(OUTPUT_REQUIREMENTS, "w") as f:

    for item in sorted(updated_requirements):
        f.write(item + "\n")

print("\n====================================")
print("Versioned requirements generated.")
print("====================================")

print(f"\nOutput File: {OUTPUT_REQUIREMENTS}")

# =====================================================
# SHOW MISSING PACKAGES
# =====================================================

if missing_packages:

    print("\nPackages NOT installed locally:")
    print("--------------------------------")

    for pkg in missing_packages:
        print(pkg)

else:

    print("\nAll packages successfully version-pinned.")
