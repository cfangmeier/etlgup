"""Main desktop application window for etlgup."""

import datetime
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk
from typing import Callable, Optional, Tuple
import pytz

from etlgup.config import AppConfig, load_config
from etlgup.gui.native_dialog import ask_native_directory
from etlgup.gui.preview_tabs import PreviewTabs
from etlgup.gui.settings_dialog import SettingsDialog
from etlgup.models import UploadBatch, build_upload_batch
from etlgup.parser import TestRunData, discover_and_parse_directory
from etlgup.uploader import UploadError, UploadResult, UploadService


class ETLGupApp:
    """ETL GUI Uploader main application controller and view."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("ETL GUI Uploader (etlgup)")
        self.root.geometry("1280x880")
        self.root.minsize(960, 650)

        self.config: AppConfig = load_config()
        self.upload_service = UploadService(self.config)

        self.current_dir: Optional[Path] = None
        self.current_run_data: Optional[TestRunData] = None
        self.current_batch: Optional[UploadBatch] = None
        self.is_busy: bool = False
        self.task_queue: queue.Queue = queue.Queue()

        self.TEST_DEFINITIONS = [
            ("baseline", "Baseline"),
            ("noisewidth", "Noisewidth"),
            ("module_iv", "Module IV"),
            ("precure_alignment", "Precure Alignment"),
            ("postcure_alignment", "Postcure Alignment"),
        ]
        self.test_vars: dict[str, tk.BooleanVar] = {
            key: tk.BooleanVar(value=True) for key, _ in self.TEST_DEFINITIONS
        }
        self.test_checkboxes: dict[str, ttk.Checkbutton] = {}

        self._apply_theme()
        self._build_ui()
        self._update_env_badge()
        self._poll_task_queue()

        self.log_info("Application initialized. Ready to load test data.")
        self.log_info(f"Target environment: {'PRODUCTION' if self.config.prod else 'STAGING'} | Location: {self.config.location} | Operator: {self.config.user_created}")

    def _apply_theme(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        # General styling
        style.configure("TButton", font=("Helvetica", 10))
        style.configure("Accent.TButton", font=("Helvetica", 10, "bold"))
        style.configure("Header.TLabel", font=("Helvetica", 11, "bold"))

    def _build_ui(self) -> None:
        # Top Container
        top_frame = ttk.Frame(self.root, padding="10 10 10 6")
        top_frame.pack(fill=tk.X, side=tk.TOP)

        # 1. Directory Bar
        dir_frame = ttk.Frame(top_frame)
        dir_frame.pack(fill=tk.X, pady=(0, 6))

        ttk.Label(dir_frame, text="Test Run Directory:", font=("Helvetica", 10, "bold")).pack(side=tk.LEFT, padx=(0, 8))
        self.dir_var = tk.StringVar()
        self.dir_entry = ttk.Entry(dir_frame, textvariable=self.dir_var, font=("Helvetica", 10))
        self.dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        self.browse_btn = ttk.Button(dir_frame, text="Browse...", command=self._browse_directory)
        self.browse_btn.pack(side=tk.LEFT, padx=(0, 4))

        self.reload_btn = ttk.Button(dir_frame, text="Reload", command=self._reload_directory)
        self.reload_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.settings_btn = ttk.Button(dir_frame, text="⚙ Settings", command=self._open_settings)
        self.settings_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.env_badge = tk.Label(
            dir_frame,
            text="STAGING",
            font=("Helvetica", 10, "bold"),
            bg="#5bc0de",
            fg="white",
            padx=8,
            pady=2,
            relief=tk.RIDGE,
        )
        self.env_badge.pack(side=tk.RIGHT)

        # 2. Metadata Bar (Editable Fields)
        meta_frame = ttk.LabelFrame(top_frame, text="Test Metadata", padding="8 6 8 6")
        meta_frame.pack(fill=tk.X, pady=(0, 4))

        # Module ID
        ttk.Label(meta_frame, text="Module:").pack(side=tk.LEFT, padx=(4, 4))
        self.meta_module_var = tk.StringVar()
        self.meta_module_entry = ttk.Entry(meta_frame, textvariable=self.meta_module_var, width=12)
        self.meta_module_entry.pack(side=tk.LEFT, padx=(0, 12))

        # Measurement Date
        ttk.Label(meta_frame, text="Date (UTC):").pack(side=tk.LEFT, padx=(4, 4))
        self.meta_date_var = tk.StringVar()
        self.meta_date_entry = ttk.Entry(meta_frame, textvariable=self.meta_date_var, width=22)
        self.meta_date_entry.pack(side=tk.LEFT, padx=(0, 12))

        # Bias Voltage
        ttk.Label(meta_frame, text="Bias (V):").pack(side=tk.LEFT, padx=(4, 4))
        self.meta_bias_var = tk.StringVar()
        self.meta_bias_entry = ttk.Entry(meta_frame, textvariable=self.meta_bias_var, width=8)
        self.meta_bias_entry.pack(side=tk.LEFT, padx=(0, 12))

        # Operator & Location info
        self.meta_user_loc_lbl = ttk.Label(meta_frame, text=f"Operator: {self.config.user_created} | Lab: {self.config.location}", foreground="#555555")
        self.meta_user_loc_lbl.pack(side=tk.LEFT, padx=(8, 12))

        self.apply_meta_btn = ttk.Button(meta_frame, text="Apply Metadata", command=self._apply_metadata)
        self.apply_meta_btn.pack(side=tk.RIGHT)

        # Center Container: Preview Tabs
        self.center_frame = ttk.Frame(self.root, padding="10 0 10 4")
        self.center_frame.pack(fill=tk.BOTH, expand=True)

        self.tabs = PreviewTabs(self.center_frame)
        self.tabs.pack(fill=tk.BOTH, expand=True)

        # Bottom Container: Actions & Log Console
        bottom_frame = ttk.Frame(self.root, padding="10 4 10 10")
        bottom_frame.pack(fill=tk.X, side=tk.BOTTOM)

        # Test Selection Frame
        self.selection_frame = ttk.LabelFrame(bottom_frame, text="Tests to Include in Upload", padding="8 5 8 5")
        self.selection_frame.pack(fill=tk.X, pady=(0, 6))

        cb_row = ttk.Frame(self.selection_frame)
        cb_row.pack(fill=tk.X)

        ttk.Label(cb_row, text="Include:", font=("Helvetica", 9, "bold")).pack(side=tk.LEFT, padx=(0, 10))

        for key, label in self.TEST_DEFINITIONS:
            cb = ttk.Checkbutton(
                cb_row,
                text=label,
                variable=self.test_vars[key],
                command=self._on_test_selection_changed,
            )
            cb.pack(side=tk.LEFT, padx=(0, 14))
            cb.config(state=tk.DISABLED)
            self.test_checkboxes[key] = cb

        btn_frame = ttk.Frame(cb_row)
        btn_frame.pack(side=tk.RIGHT)

        self.select_all_btn = ttk.Button(btn_frame, text="Select All", width=10, command=self._select_all_tests)
        self.select_all_btn.pack(side=tk.LEFT, padx=(0, 4))
        self.select_all_btn.config(state=tk.DISABLED)

        self.deselect_all_btn = ttk.Button(btn_frame, text="Deselect All", width=11, command=self._deselect_all_tests)
        self.deselect_all_btn.pack(side=tk.LEFT, padx=(0, 10))
        self.deselect_all_btn.config(state=tk.DISABLED)

        self.selection_summary_lbl = ttk.Label(
            btn_frame,
            text="No data loaded",
            font=("Helvetica", 9, "italic"),
            foreground="#555555",
        )
        self.selection_summary_lbl.pack(side=tk.LEFT)

        # Action Buttons row
        action_bar = ttk.Frame(bottom_frame)
        action_bar.pack(fill=tk.X, pady=(0, 6))

        self.dry_run_btn = ttk.Button(action_bar, text="🔍 Run Dry Run", command=self._trigger_dry_run)
        self.dry_run_btn.pack(side=tk.LEFT, padx=(0, 8))

        self.upload_btn = ttk.Button(action_bar, text="🚀 Upload to ETL", style="Accent.TButton", command=self._trigger_upload)
        self.upload_btn.pack(side=tk.LEFT, padx=(0, 16))

        self.progress_bar = ttk.Progressbar(action_bar, mode="indeterminate", length=220)

        self.status_label = ttk.Label(action_bar, text="Ready", font=("Helvetica", 10))
        self.status_label.pack(side=tk.RIGHT, padx=4)

        # Log Console
        self.log_text = scrolledtext.ScrolledText(
            bottom_frame,
            height=7,
            wrap=tk.WORD,
            font=("Monospace", 9),
            background="#222222",
            foreground="#e0e0e0",
            insertbackground="white",
        )
        self.log_text.pack(fill=tk.X)

        self.log_text.tag_config("INFO", foreground="#7ec8e3")
        self.log_text.tag_config("SUCCESS", foreground="#5cb85c")
        self.log_text.tag_config("WARNING", foreground="#f0ad4e")
        self.log_text.tag_config("ERROR", foreground="#d9534f")

    def _update_env_badge(self) -> None:
        if self.config.prod:
            self.env_badge.config(text="PRODUCTION", bg="#d9534f", fg="white")
        else:
            self.env_badge.config(text="STAGING", bg="#5bc0de", fg="white")
        self.meta_user_loc_lbl.config(text=f"Operator: {self.config.user_created} | Lab: {self.config.location}")

    def log(self, level: str, msg: str) -> None:
        """Append a message to the scrolling log console with timestamp."""
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{ts}] [{level}] {msg}\n", level)
        self.log_text.see(tk.END)

    def log_info(self, msg: str) -> None:
        self.log("INFO", msg)

    def log_success(self, msg: str) -> None:
        self.log("SUCCESS", msg)

    def log_warn(self, msg: str) -> None:
        self.log("WARNING", msg)

    def log_error(self, msg: str) -> None:
        self.log("ERROR", msg)

    def set_busy(self, busy: bool, message: str = "") -> None:
        """Toggle UI busy state and indeterminate progress animation."""
        self.is_busy = busy
        state = tk.DISABLED if busy else tk.NORMAL
        self.browse_btn.config(state=state)
        self.reload_btn.config(state=state)
        self.dry_run_btn.config(state=state)
        self.upload_btn.config(state=state)
        self.apply_meta_btn.config(state=state)

        if busy:
            for cb in self.test_checkboxes.values():
                cb.config(state=tk.DISABLED)
            self.select_all_btn.config(state=tk.DISABLED)
            self.deselect_all_btn.config(state=tk.DISABLED)
            self.progress_bar.pack(side=tk.LEFT, padx=(0, 16))
            self.progress_bar.start(10)
            if message:
                self.status_label.config(text=message)
        else:
            for key, cb in self.test_checkboxes.items():
                if self._is_test_available(key):
                    cb.config(state=tk.NORMAL)
            avail = any(self._is_test_available(k) for k in self.test_vars)
            self.select_all_btn.config(state=tk.NORMAL if avail else tk.DISABLED)
            self.deselect_all_btn.config(state=tk.NORMAL if avail else tk.DISABLED)
            self.progress_bar.stop()
            self.progress_bar.pack_forget()
            self.status_label.config(text=message or "Ready")

    def _is_test_available(self, key: str) -> bool:
        """Check whether a given test exists and was successfully loaded in the current batch."""
        if not self.current_batch:
            return False
        if key == "baseline":
            return self.current_batch.baseline is not None
        elif key == "noisewidth":
            return self.current_batch.noisewidth is not None
        elif key == "module_iv":
            return self.current_batch.module_iv is not None or len(self.current_batch.module_ivs) > 0
        elif key == "precure_alignment":
            return self.current_batch.precure_alignment is not None
        elif key == "postcure_alignment":
            return self.current_batch.postcure_alignment is not None
        return False

    def _get_selected_keys(self) -> set[str]:
        """Return the set of keys for tests that are available and currently checked."""
        return {
            key for key, var in self.test_vars.items()
            if var.get() and self._is_test_available(key)
        }

    def _get_active_batch(self) -> Optional[UploadBatch]:
        """Construct an UploadBatch filtered to contain only currently selected tests."""
        if not self.current_batch:
            return None
        return self.current_batch.filter_by_keys(self._get_selected_keys())

    def _update_test_selection_controls(self, reset_selection: bool = False) -> None:
        """Enable or disable checkboxes based on test availability in current batch."""
        has_any_available = False
        for key, cb in self.test_checkboxes.items():
            avail = self._is_test_available(key)
            if avail:
                has_any_available = True
                cb.config(state=tk.NORMAL)
                if reset_selection:
                    self.test_vars[key].set(True)
            else:
                cb.config(state=tk.DISABLED)
                self.test_vars[key].set(False)

        btn_state = tk.NORMAL if (has_any_available and not self.is_busy) else tk.DISABLED
        self.select_all_btn.config(state=btn_state)
        self.deselect_all_btn.config(state=btn_state)
        self._on_test_selection_changed()

    def _on_test_selection_changed(self) -> None:
        """Recalculate selected counts and refresh UI status and overview table."""
        active_batch = self._get_active_batch()
        active_count = active_batch.total_count if active_batch else 0
        selected_keys = self._get_selected_keys()
        selected_tests_count = len(selected_keys)
        avail_tests_count = sum(1 for key, _ in self.TEST_DEFINITIONS if self._is_test_available(key))

        if not self.current_batch or avail_tests_count == 0:
            self.selection_summary_lbl.config(text="No data loaded")
            self.status_label.config(text="Ready")
        elif selected_tests_count == 0:
            self.selection_summary_lbl.config(text=f"0 of {avail_tests_count} tests selected (0 records)")
            self.status_label.config(text="No tests selected for upload")
        else:
            rec_str = f"{active_count} record{'s' if active_count != 1 else ''}"
            self.selection_summary_lbl.config(text=f"{selected_tests_count} of {avail_tests_count} tests selected ({rec_str})")
            if not self.is_busy:
                self.status_label.config(text=f"{rec_str} ready")

        if self.current_run_data and self.current_batch and active_batch is not None:
            self.tabs.update_selection_summary(
                run_data=self.current_run_data,
                total_batch=self.current_batch,
                selected_keys=selected_keys,
                active_batch=active_batch,
            )

    def _select_all_tests(self) -> None:
        """Select all available tests in the loaded batch."""
        for key in self.test_vars:
            if self._is_test_available(key):
                self.test_vars[key].set(True)
        self._on_test_selection_changed()

    def _deselect_all_tests(self) -> None:
        """Deselect all tests."""
        for key in self.test_vars:
            self.test_vars[key].set(False)
        self._on_test_selection_changed()

    def _poll_task_queue(self) -> None:
        """Process pending callbacks from worker threads on main Tk thread."""
        try:
            while True:
                callback, args = self.task_queue.get_nowait()
                try:
                    callback(*args)
                except Exception as e:
                    self.log_error(f"Error handling task queue callback: {e}")
        except queue.Empty:
            pass

        try:
            if self.root.winfo_exists():
                self.root.after(50, self._poll_task_queue)
        except Exception:
            pass

    def _browse_directory(self) -> None:
        initial = str(self.current_dir) if self.current_dir else str(Path.home())
        selected = ask_native_directory(title="Select Electronics Test Directory", initial_dir=initial)
        if selected:
            self.dir_var.set(selected)
            self._load_directory(Path(selected))

    def _reload_directory(self) -> None:
        raw_path = self.dir_var.get().strip()
        if not raw_path:
            messagebox.showinfo("Select Directory", "Please select or enter a valid test directory path.")
            return
        p = Path(raw_path)
        if not p.is_dir():
            messagebox.showerror("Error", f"Directory does not exist: {p}")
            return
        self._load_directory(p)

    def _load_directory(self, dir_path: Path) -> None:
        self.current_dir = dir_path
        self.set_busy(True, f"Loading {dir_path.name}...")
        self.log_info(f"Scanning directory: {dir_path}")

        def _worker() -> None:
            try:
                run_data = discover_and_parse_directory(dir_path)
                batch = build_upload_batch(
                    run_data=run_data,
                    location=self.config.location,
                    user_created=self.config.user_created,
                )
                self.task_queue.put((self._on_load_success, (run_data, batch)))
            except Exception as exc:
                self.task_queue.put((self._on_load_error, (exc,)))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_load_success(self, run_data: TestRunData, batch: UploadBatch) -> None:
        self.set_busy(False, "Loaded")
        self.current_run_data = run_data
        self.current_batch = batch

        # Populate metadata fields
        meta = run_data.metadata
        self.meta_module_var.set(meta.module or "")
        if meta.measurement_date:
            date_str = meta.measurement_date.strftime("%Y-%m-%d %H:%M:%S UTC")
            self.meta_date_var.set(date_str)
        else:
            self.meta_date_var.set("")
        self.meta_bias_var.set(str(meta.bias_volts) if meta.bias_volts is not None else "")

        # Enable selection controls and default all available tests to selected
        self._update_test_selection_controls(reset_selection=True)

        # Populate tabs and render plots
        self.tabs.set_test_run(
            run_data=run_data,
            batch=batch,
            selected_keys=self._get_selected_keys(),
            active_batch=self._get_active_batch(),
        )

        iv_count = len(batch.module_ivs)
        align_count = len(batch.subassembly_alignments)
        self.log_success(
            f"Successfully parsed {dir_name_only(run_data.directory)}: "
            f"{len(run_data.baseline_matrices)} baseline, {len(run_data.noisewidth_matrices)} noisewidth, "
            f"{iv_count} IV, {align_count} alignment ({batch.total_count} total items)."
        )
        for w in run_data.warnings:
            self.log_warn(w)

    def _on_load_error(self, exc: Exception) -> None:
        self.set_busy(False, "Error")
        self.log_error(f"Failed to load directory: {exc}")
        messagebox.showerror("Parsing Error", f"Failed to parse test files:\n{exc}")

    def _apply_metadata(self) -> None:
        """Re-generate batch models using edited metadata without re-reading files."""
        if not self.current_run_data:
            messagebox.showinfo("No Data", "No test run loaded yet. Please select a folder first.")
            return

        new_module = self.meta_module_var.get().strip() or None
        date_str = self.meta_date_var.get().strip()
        parsed_date: Optional[datetime.datetime] = None
        if date_str:
            clean_str = date_str.replace("UTC", "").strip()
            try:
                dt = datetime.datetime.fromisoformat(clean_str)
                parsed_date = dt if dt.tzinfo else pytz.utc.localize(dt)
            except Exception as e:
                messagebox.showerror("Invalid Date", f"Could not parse measurement date '{date_str}':\n{e}\nFormat: YYYY-MM-DD HH:MM:SS")
                return

        bias_str = self.meta_bias_var.get().strip()
        parsed_bias: Optional[float] = None
        if bias_str:
            try:
                parsed_bias = float(bias_str)
            except ValueError:
                messagebox.showerror("Invalid Bias", f"Bias voltage must be a number, got '{bias_str}'.")
                return

        try:
            self.current_batch = build_upload_batch(
                run_data=self.current_run_data,
                location=self.config.location,
                user_created=self.config.user_created,
                module=new_module,
                measurement_date=parsed_date,
                bias_volts=parsed_bias,
            )
            # Update metadata in run_data for display
            if new_module:
                self.current_run_data.metadata.module = new_module
            if parsed_date:
                self.current_run_data.metadata.measurement_date = parsed_date
            if parsed_bias is not None:
                self.current_run_data.metadata.bias_volts = parsed_bias

            self._update_test_selection_controls(reset_selection=False)
            self.tabs.set_test_run(
                run_data=self.current_run_data,
                batch=self.current_batch,
                selected_keys=self._get_selected_keys(),
                active_batch=self._get_active_batch(),
            )
            self.log_info(f"Updated metadata: module={new_module}, date={parsed_date}, bias={parsed_bias}V")
        except Exception as e:
            self.log_error(f"Failed to apply metadata: {e}")
            messagebox.showerror("Validation Error", f"Failed to validate models with updated metadata:\n{e}")

    def _open_settings(self) -> None:
        def _on_save(updated_config: AppConfig) -> None:
            self.config = updated_config
            self.upload_service = UploadService(self.config)
            self._update_env_badge()
            self.log_info(f"Settings saved. Environment: {'PRODUCTION' if self.config.prod else 'STAGING'}, Location: {self.config.location}")
            # Refresh current batch if loaded to apply new user/location
            if self.current_run_data:
                self._apply_metadata()

        SettingsDialog(self.root, self.config, on_save=_on_save)

    def _trigger_dry_run(self) -> None:
        if not self.current_batch or self.current_batch.total_count == 0:
            messagebox.showinfo("Dry Run", "No test data loaded. Please select a valid directory first.")
            return

        active_batch = self._get_active_batch()
        if not active_batch or active_batch.total_count == 0:
            messagebox.showwarning("Dry Run", "No tests selected for upload. Please select at least one test.")
            return

        self.set_busy(True, "Running dry-run validation...")
        selected_names = [label for key, label in self.TEST_DEFINITIONS if key in self._get_selected_keys()]
        names_str = ", ".join(selected_names)
        self.log_info(f"Starting dry-run validation for {active_batch.total_count} record(s) ({names_str})...")

        def _worker() -> None:
            try:
                res = self.upload_service.execute_dry_run(active_batch)
                self.task_queue.put((self._on_dry_run_success, (res,)))
            except Exception as exc:
                self.task_queue.put((self._on_upload_error, (exc,)))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_dry_run_success(self, res: UploadResult) -> None:
        self.set_busy(False, "Dry Run OK")
        self.log_success(res.message)
        messagebox.showinfo("Dry Run Successful", f"Validation passed!\n{res.count} records ready for upload.")

    def _trigger_upload(self) -> None:
        if not self.current_batch or self.current_batch.total_count == 0:
            messagebox.showinfo("Upload", "No test data loaded. Please select a valid directory first.")
            return

        active_batch = self._get_active_batch()
        if not active_batch or active_batch.total_count == 0:
            messagebox.showwarning("Upload", "No tests selected for upload. Please select at least one test.")
            return

        module = self.meta_module_var.get().strip() or (self.current_run_data.metadata.module if self.current_run_data else "")
        errors = self.config.validate_for_upload(module=module)
        if errors:
            msg = "Cannot upload due to missing configuration:\n" + "\n".join(f"• {e}" for e in errors)
            self.log_error(msg)
            messagebox.showwarning("Prerequisites Missing", msg)
            return

        selected_names = [label for key, label in self.TEST_DEFINITIONS if key in self._get_selected_keys()]
        names_str = ", ".join(selected_names)
        # Confirmation dialog
        env_name = "PRODUCTION" if self.config.prod else "STAGING"
        confirm_msg = (
            f"Are you sure you want to upload {active_batch.total_count} record(s) ({names_str}) "
            f"for module '{module}' to CERN ETL [{env_name}] database?"
        )
        if self.config.prod:
            confirm_msg = "⚠️ ATTENTION: You are uploading to the LIVE PRODUCTION database!\n\n" + confirm_msg

        if not messagebox.askyesno("Confirm Upload", confirm_msg, icon=messagebox.WARNING if self.config.prod else messagebox.QUESTION):
            return

        self.set_busy(True, f"Uploading to {env_name}...")
        self.log_info(f"Initiating live upload of {active_batch.total_count} record(s) ({names_str}) to {env_name} ETL database...")

        def _worker() -> None:
            try:
                res = self.upload_service.execute_upload(active_batch, module=module)
                self.task_queue.put((self._on_upload_success, (res,)))
            except Exception as exc:
                self.task_queue.put((self._on_upload_error, (exc,)))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_upload_success(self, res: UploadResult) -> None:
        self.set_busy(False, "Upload Complete")
        self.log_success(res.message)
        messagebox.showinfo("Upload Successful", f"Success!\n{res.message}")

    def _on_upload_error(self, exc: Exception) -> None:
        self.set_busy(False, "Upload Failed")
        msg = str(exc)
        self.log_error(f"Operation failed: {msg}")
        messagebox.showerror("Operation Failed", f"An error occurred:\n{msg}")


def dir_name_only(p: Path) -> str:
    return p.name or str(p)


def launch_gui() -> None:
    """Entrypoint function to run Tkinter mainloop."""
    root = tk.Tk()
    app = ETLGupApp(root)
    root.mainloop()
