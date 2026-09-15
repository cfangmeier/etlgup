"""Native dialog helpers for etlgup."""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def ask_native_directory(
    title: str = "Select Electronics Test Directory",
    initial_dir: Optional[str] = None,
) -> Optional[str]:
    """Open a platform-native directory picker dialog, with graceful fallback to Tkinter.

    Uses crossfiledialog (invoking Zenity or KDialog on Linux, native Shell dialogs on
    Windows, and AppleScript on macOS). If the platform-native dialog cannot be opened
    or fails, it falls back to Tkinter's filedialog.
    """
    try:
        import crossfiledialog

        start = str(initial_dir) if initial_dir else None
        res = crossfiledialog.choose_folder(title=title, start_dir=start)
        if res:
            return str(res).strip()
        # If user cancelled, res is empty string or None
        if res == "" or res is None:
            return None
    except Exception as exc:
        # Check if macOS user cancelled
        if "User canceled" in str(exc):
            return None
        logger.warning(
            "Native folder dialog unavailable or failed (%s); falling back to Tkinter",
            exc,
        )

    try:
        from tkinter import filedialog

        tk_res = filedialog.askdirectory(title=title, initialdir=initial_dir)
        return str(tk_res).strip() if tk_res else None
    except Exception as exc:
        logger.error("Fallback Tkinter folder dialog failed: %s", exc)
        return None
