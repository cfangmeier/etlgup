"""Build script to produce standalone etlgup executable via PyInstaller."""

import argparse
import os
from pathlib import Path
import shutil
import sys
import PyInstaller.__main__


def build(onefile: bool = True, debug: bool = False) -> None:
    root_dir = Path(__file__).resolve().parent
    entrypoint = root_dir / "main.py"
    dist_target = root_dir / "dist" / "etlgup"

    # Clean existing dist target if type changed (dir vs file)
    if dist_target.exists():
        if dist_target.is_dir():
            shutil.rmtree(dist_target)
        else:
            dist_target.unlink()

    args = [
        str(entrypoint),
        "--name=etlgup",
        "--clean",
        "--noconfirm",
        "--collect-all=etlup",
        "--collect-all=crossfiledialog",
        "--hidden-import=matplotlib.backends.backend_tkagg",
        "--hidden-import=yaml",
        "--hidden-import=pydantic",
        "--hidden-import=pytz",
        "--hidden-import=requests",
        "--hidden-import=dotenv",
        "--hidden-import=PIL",
        "--hidden-import=PIL.ImageTk",
    ]

    if onefile:
        args.append("--onefile")
    else:
        args.append("--onedir")

    if not debug:
        args.append("--windowed")

    print(f"Running PyInstaller with arguments:\n{' '.join(args)}")
    PyInstaller.__main__.run(args)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build etlgup standalone executable")
    parser.add_argument("--onedir", action="store_true", help="Build directory bundle instead of single-file executable")
    parser.add_argument("--onefile", action="store_true", default=True, help="Build single-file executable (default)")
    parser.add_argument("--debug", action="store_true", help="Keep console window open for debugging")
    parsed_args = parser.parse_args()

    onefile = not parsed_args.onedir
    build(onefile=onefile, debug=parsed_args.debug)
