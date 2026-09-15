from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from etlgup.gui.native_dialog import ask_native_directory
from etlgup.gui.app import ETLGupApp

SAMPLE_DIR = Path("/home/caleb/Downloads/MP40229/2026-09-15-12-03-51_AFTER-BL-100V")


def test_ask_native_directory_success(monkeypatch):
    mock_choose = MagicMock(return_value="/some/selected/path")
    monkeypatch.setattr("crossfiledialog.choose_folder", mock_choose)

    res = ask_native_directory(title="Select Folder", initial_dir="/start/here")
    assert res == "/some/selected/path"
    mock_choose.assert_called_once_with(title="Select Folder", start_dir="/start/here")


def test_ask_native_directory_user_cancel_empty_string(monkeypatch):
    mock_choose = MagicMock(return_value="")
    monkeypatch.setattr("crossfiledialog.choose_folder", mock_choose)

    res = ask_native_directory()
    assert res is None


def test_ask_native_directory_user_cancel_none(monkeypatch):
    mock_choose = MagicMock(return_value=None)
    monkeypatch.setattr("crossfiledialog.choose_folder", mock_choose)

    res = ask_native_directory()
    assert res is None


def test_ask_native_directory_user_cancel_exception(monkeypatch):
    def _raise(*args, **kwargs):
        raise RuntimeError("execution error: User canceled. (-128)")

    monkeypatch.setattr("crossfiledialog.choose_folder", _raise)

    res = ask_native_directory()
    assert res is None


def test_ask_native_directory_fallback_on_error(monkeypatch):
    def _raise(*args, **kwargs):
        raise RuntimeError("No native tool found")

    monkeypatch.setattr("crossfiledialog.choose_folder", _raise)

    with patch("tkinter.filedialog.askdirectory", return_value="/fallback/path") as mock_tk:
        res = ask_native_directory(title="Pick", initial_dir="/init")
        assert res == "/fallback/path"
        mock_tk.assert_called_once_with(title="Pick", initialdir="/init")


def test_gui_browse_directory(tk_root, monkeypatch):
    app = ETLGupApp(tk_root)

    # Simulate user selecting SAMPLE_DIR via native dialog
    with patch("etlgup.gui.app.ask_native_directory", return_value=str(SAMPLE_DIR)):
        app._browse_directory()

    assert app.dir_var.get() == str(SAMPLE_DIR)
    assert app.current_dir == SAMPLE_DIR
