"""Build script to produce standalone etlgup executable via PyInstaller."""

import argparse
import os
from pathlib import Path
import sys
import PyInstaller.__main__


def build(onefile: bool = False, debug: bool = False) -> None:
    root_dir = Path(__file__).resolve().parent
    entrypoint = root_dir / "main.py"

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
    parser.add_argument("--onefile", action="store_true", help="Build single-file executable")
    parser.add_argument("--debug", action="store_true", help="Keep console window open for debugging")
    parsed_args = parser.parse_args()

    build(onefile=parsed_args.onefile, debug=parsed_args.debug)
