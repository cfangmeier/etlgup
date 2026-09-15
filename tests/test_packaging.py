import os
from pathlib import Path
import subprocess
import pytest


def test_build_script_and_spec_exist():
    root = Path(__file__).resolve().parent.parent
    build_script = root / "build_installer.py"
    spec_file = root / "etlgup.spec"
    assert build_script.is_file(), "build_installer.py should exist"
    assert spec_file.is_file(), "etlgup.spec should exist"


def test_packaged_executable_launch():
    root = Path(__file__).resolve().parent.parent
    exe = root / "dist" / "etlgup" / "etlgup"
    if not exe.is_file():
        pytest.skip("Packaged binary dist/etlgup/etlgup not yet built")

    assert os.access(exe, os.X_OK), "Packaged binary should be executable"

    # Run for 2 seconds to ensure it starts without missing imports or crashes
    proc = subprocess.Popen([str(exe)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        proc.wait(timeout=2)
        # If it exited within 2 seconds, check returncode
        stdout, stderr = proc.communicate()
        assert proc.returncode == 0, f"Process crashed unexpectedly: {stderr.decode()}"
    except subprocess.TimeoutExpired:
        # Still running normally in event loop, which means success
        proc.terminate()
        proc.wait()
