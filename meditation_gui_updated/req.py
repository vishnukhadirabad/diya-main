import os
import re
import csv
import pkg_resources
from collections import defaultdict

# =========================================================
# CONFIGURATION
# =========================================================

PROJECT_ROOT = "/home/prayojaka/Desktop/meditation_gui_updated"

OUTPUT_REQUIREMENTS = "requirements.txt"
OUTPUT_CSV = "dependency_report.csv"
OUTPUT_MD = "dependency_report.md"

# Common standard library modules to ignore
STD_LIBS = {
    "os", "sys", "math", "json", "time", "datetime",
    "random", "logging", "subprocess", "threading",
    "multiprocessing", "pathlib", "typing", "collections",
    "itertools", "functools", "shutil", "tempfile",
    "glob", "re", "csv", "sqlite3", "socket",
    "pickle", "traceback", "warnings", "inspect",
    "argparse", "hashlib", "uuid", "asyncio"
}

# Common bash commands to track
BASH_COMMANDS = {
    "python", "python3", "pip", "pip3",
    "docker", "docker-compose",
    "ffmpeg", "curl", "wget",
    "git", "mysql", "psql",
    "redis-server", "mongod",
    "java", "node", "npm",
    "systemctl", "service",
    "nvidia-smi", "conda"
}

# =========================================================
# PACKAGE MAPPING
# =========================================================

# Some imports differ from pip package names
PACKAGE_MAPPING = {
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "PIL": "Pillow",
    "yaml": "PyYAML",
    "Crypto": "pycryptodome",
    "torchvision": "torchvision",
    "torchaudio": "torchaudio"
}

# =========================================================
# REGEX PATTERNS
# =========================================================

IMPORT_RE = re.compile(
    r'^\s*(?:import|from)\s+([a-zA-Z0-9_\.]+)'
)

COMMAND_RE = re.compile(
    r'^\s*([a-zA-Z0-9_\-]+)'
)

# =========================================================
# STORAGE
# =========================================================

dependencies = set()
report_rows = []

# =========================================================
# PYTHON FILE PARSER
# =========================================================

def parse_python_file(filepath):
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            match = IMPORT_RE.match(line)

            if match:
                module = match.group(1).split('.')[0]

                if module not in STD_LIBS:
                    package = PACKAGE_MAPPING.get(module, module)

                    dependencies.add(package)

                    report_rows.append({
                        "file": filepath,
                        "type": "Python",
                        "dependency": package,
                        "line": line.strip()
                    })

# =========================================================
# BASH FILE PARSER
# =========================================================

def parse_bash_file(filepath):
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:

            line = line.strip()

            if not line or line.startswith("#"):
                continue

            match = COMMAND_RE.match(line)

            if match:
                cmd = match.group(1)

                if cmd in BASH_COMMANDS:

                    dependencies.add(cmd)

                    report_rows.append({
                        "file": filepath,
                        "type": "Bash",
                        "dependency": cmd,
                        "line": line
                    })

# =========================================================
# DIRECTORY WALKER
# =========================================================

for root, dirs, files in os.walk(PROJECT_ROOT):

    # Skip hidden/system folders
    dirs[:] = [
        d for d in dirs
        if d not in {
            ".git", "__pycache__", ".idea",
            ".vscode", "venv", ".venv",
            "node_modules"
        }
    ]

    for file in files:

        filepath = os.path.join(root, file)

        try:

            if file.endswith(".py"):
                parse_python_file(filepath)

            elif file.endswith(".sh"):
                parse_bash_file(filepath)

        except Exception as e:
            print(f"Error reading {filepath}: {e}")

# =========================================================
# WRITE requirements.txt
# =========================================================

with open(OUTPUT_REQUIREMENTS, "w") as f:
    for dep in sorted(dependencies):
        f.write(dep + "\n")

# =========================================================
# WRITE CSV REPORT
# =========================================================

with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as csvfile:

    writer = csv.DictWriter(
        csvfile,
        fieldnames=["file", "type", "dependency", "line"]
    )

    writer.writeheader()

    for row in report_rows:
        writer.writerow(row)

# =========================================================
# WRITE MARKDOWN REPORT
# =========================================================

with open(OUTPUT_MD, "w", encoding="utf-8") as f:

    f.write("# Dependency Report\n\n")

    f.write("| File | Type | Dependency | Source Line |\n")
    f.write("|------|------|-------------|-------------|\n")

    for row in report_rows:
        f.write(
            f"| {row['file']} "
            f"| {row['type']} "
            f"| {row['dependency']} "
            f"| `{row['line']}` |\n"
        )

print("\nDependency extraction complete.\n")

print(f"Generated:")
print(f" - {OUTPUT_REQUIREMENTS}")
print(f" - {OUTPUT_CSV}")
print(f" - {OUTPUT_MD}")
