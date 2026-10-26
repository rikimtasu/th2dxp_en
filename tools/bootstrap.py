"""Fetch pinned public tools. Never downloads game data or emulators."""
from pathlib import Path
import json
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    upstreams = json.loads((ROOT / "upstreams.json").read_text(encoding="utf-8"))
    for name, source in upstreams.items():
        dest = ROOT / "vendor" / name
        if not dest.exists():
            subprocess.run(["git", "clone", source["url"], str(dest)], check=True)
            subprocess.run(["git", "-C", str(dest), "checkout", "--detach", source["revision"]], check=True)
        actual = subprocess.check_output(["git", "-C", str(dest), "rev-parse", "HEAD"], text=True).strip()
        if actual != source["revision"]:
            raise SystemExit(f"{name}: expected {source['revision']}, got {actual}; existing checkout left untouched")
        print(f"{name}: {actual}")
    print("Tools ready. Install Python dependencies: python -m pip install -r requirements.txt")


if __name__ == "__main__":
    main()
