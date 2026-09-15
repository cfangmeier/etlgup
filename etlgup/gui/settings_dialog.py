"""Settings dialog for configuring user, location, tokens, and target environment."""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable, Optional

from etlgup.config import AppConfig, save_config


class SettingsDialog(tk.Toplevel):
    """Modal dialog for editing application preferences and credentials."""

    def __init__(self, parent: tk.Tk | tk.Toplevel, config: AppConfig, on_save: Optional[Callable[[AppConfig], None]] = None):
        super().__init__(parent)
        self.parent = parent
        self.config = config
        self.on_save = on_save

        self.title("Settings & Credentials")
        self.geometry("520x420")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._init_ui()
        self._populate_fields()

        # Center on parent
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _init_ui(self) -> None:
        pad_opts = {"padx": 16, "pady": 8}

        main_frame = ttk.Frame(self, padding="16 16 16 16")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Header
        title_lbl = ttk.Label(main_frame, text="Application Settings", font=("Helvetica", 14, "bold"))
        title_lbl.grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 16))

        # Username / Operator
        ttk.Label(main_frame, text="Operator Name (user_created):").grid(row=1, column=0, sticky=tk.W, pady=4)
        self.user_var = tk.StringVar()
        self.user_entry = ttk.Entry(main_frame, textvariable=self.user_var, width=32)
        self.user_entry.grid(row=1, column=1, sticky=tk.EW, pady=4)

        # Lab Location
        ttk.Label(main_frame, text="Lab Location:").grid(row=2, column=0, sticky=tk.W, pady=4)
        self.loc_var = tk.StringVar()
        self.loc_entry = ttk.Entry(main_frame, textvariable=self.loc_var, width=32)
        self.loc_entry.grid(row=2, column=1, sticky=tk.EW, pady=4)

        # ETL API Token
        ttk.Label(main_frame, text="ETL API Token:").grid(row=3, column=0, sticky=tk.W, pady=4)
        token_frame = ttk.Frame(main_frame)
        token_frame.grid(row=3, column=1, sticky=tk.EW, pady=4)
        self.token_var = tk.StringVar()
        self.token_entry = ttk.Entry(token_frame, textvariable=self.token_var, show="*", width=24)
        self.token_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.show_token_var = tk.BooleanVar(value=False)
        self.toggle_btn = ttk.Checkbutton(token_frame, text="Show", variable=self.show_token_var, command=self._toggle_token_visibility)
        self.toggle_btn.pack(side=tk.RIGHT, padx=(6, 0))

        # Target Environment (Staging vs Prod)
        ttk.Label(main_frame, text="Environment:").grid(row=4, column=0, sticky=tk.W, pady=6)
        env_frame = ttk.Frame(main_frame)
        env_frame.grid(row=4, column=1, sticky=tk.W, pady=6)
        self.prod_var = tk.BooleanVar(value=False)
        self.staging_rb = ttk.Radiobutton(env_frame, text="Staging (Test)", variable=self.prod_var, value=False)
        self.staging_rb.pack(side=tk.LEFT, padx=(0, 12))
        self.prod_rb = ttk.Radiobutton(env_frame, text="Production", variable=self.prod_var, value=True)
        self.prod_rb.pack(side=tk.LEFT)

        # Custom Domain Override
        ttk.Label(main_frame, text="Custom API Domain (optional):").grid(row=5, column=0, sticky=tk.W, pady=4)
        self.domain_var = tk.StringVar()
        self.domain_entry = ttk.Entry(main_frame, textvariable=self.domain_var, width=32)
        self.domain_entry.grid(row=5, column=1, sticky=tk.EW, pady=4)

        main_frame.columnconfigure(1, weight=1)

        # Buttons Frame
        btn_frame = ttk.Frame(self, padding="16 12 16 16")
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)

        cancel_btn = ttk.Button(btn_frame, text="Cancel", command=self.destroy)
        cancel_btn.pack(side=tk.RIGHT, padx=(8, 0))

        save_btn = ttk.Button(btn_frame, text="Save Settings", command=self._save)
        save_btn.pack(side=tk.RIGHT)

    def _populate_fields(self) -> None:
        self.user_var.set(self.config.user_created or "")
        self.loc_var.set(self.config.location or "BU")
        self.token_var.set(self.config.api_token or "")
        self.prod_var.set(self.config.prod)
        self.domain_var.set(self.config.custom_domain or "")

    def _toggle_token_visibility(self) -> None:
        if self.show_token_var.get():
            self.token_entry.config(show="")
        else:
            self.token_entry.config(show="*")

    def _save(self) -> None:
        user = self.user_var.get().strip()
        loc = self.loc_var.get().strip()
        token = self.token_var.get().strip()
        is_prod = self.prod_var.get()
        custom_domain = self.domain_var.get().strip() or None

        if not loc:
            messagebox.showwarning("Validation Error", "Lab location cannot be empty.", parent=self)
            return
        if not user:
            messagebox.showwarning("Validation Error", "Operator name cannot be empty.", parent=self)
            return

        self.config.user_created = user
        self.config.location = loc
        self.config.api_token = token
        self.config.prod = is_prod
        self.config.custom_domain = custom_domain

        save_config(self.config)

        if self.on_save:
            self.on_save(self.config)

        self.destroy()
