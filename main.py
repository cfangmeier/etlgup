"""Application entrypoint for etlgup."""

import sys
from pathlib import Path
import tkinter as tk

from etlgup.gui.app import ETLGupApp


def main() -> None:
    root = tk.Tk()
    app = ETLGupApp(root)

    # If folder passed via command line, auto-load it
    if len(sys.argv) > 1:
        initial_dir = Path(sys.argv[1])
        if initial_dir.is_dir():
            app.dir_var.set(str(initial_dir))
            app._load_directory(initial_dir)

    root.mainloop()


if __name__ == "__main__":
    main()
