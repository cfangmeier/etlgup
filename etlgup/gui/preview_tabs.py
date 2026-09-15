"""Tabbed notebook previewing test overview and in-memory rendered plot images."""

import io
import tkinter as tk
from tkinter import ttk
from typing import Any, Dict, List, Optional, Set, Tuple
import matplotlib.pyplot as plt
from PIL import Image, ImageTk

from etlgup.models import UploadBatch
from etlgup.parser import TestRunData


def render_figure_to_image(fig: plt.Figure, dpi: Optional[int] = None) -> Image.Image:
    """Render a Matplotlib figure directly to a PIL Image using Agg RGBA buffer and close the figure.

    This avoids PNG encoding/decoding overhead and avoids double-draw layout cycles from bbox_inches='tight'.
    """
    try:
        if dpi is not None:
            fig.set_dpi(dpi)
        fig.canvas.draw()
        rgba = fig.canvas.buffer_rgba()
        w, h = fig.canvas.get_width_height()
        return Image.frombuffer("RGBA", (w, h), rgba, "raw", "RGBA", 0, 1).copy()
    finally:
        plt.close(fig)


def render_figure_to_png_image(fig: plt.Figure, dpi: Optional[int] = None) -> Image.Image:
    """Backward-compatible wrapper for rendering a figure to a PIL Image."""
    return render_figure_to_image(fig, dpi=dpi)


class ScalingImageCanvas(tk.Canvas):
    """Tkinter Canvas displaying a PIL Image, automatically scaling to fit preserving aspect ratio."""

    def __init__(self, parent: tk.Widget, **kwargs: Any):
        kwargs.setdefault("bg", "#ffffff")
        kwargs.setdefault("highlightthickness", 0)
        super().__init__(parent, **kwargs)

        self.original_image: Optional[Image.Image] = None
        self._tk_image: Optional[ImageTk.PhotoImage] = None
        self._last_canvas_size: Tuple[int, int] = (0, 0)
        self._placeholder_text: Optional[str] = None
        self._resize_timer: Optional[str] = None

        self.bind("<Configure>", self._on_configure)

    def set_placeholder(self, text: str) -> None:
        """Clear image and display centered placeholder text."""
        self._cancel_timer()
        self.original_image = None
        self._tk_image = None
        self._placeholder_text = text
        self._last_canvas_size = (0, 0)
        self._draw_placeholder()

    def set_image(self, image: Image.Image) -> None:
        """Set a new PIL Image and render it scaled to fit."""
        self._cancel_timer()
        self._placeholder_text = None
        self.original_image = image
        self._last_canvas_size = (0, 0)
        self.redraw()

    def clear(self) -> None:
        """Reset the canvas to empty state."""
        self._cancel_timer()
        self.original_image = None
        self._tk_image = None
        self._placeholder_text = None
        self._last_canvas_size = (0, 0)
        self.delete("all")

    def _cancel_timer(self) -> None:
        if self._resize_timer is not None:
            try:
                self.after_cancel(self._resize_timer)
            except Exception:
                pass
            self._resize_timer = None

    def _on_configure(self, event: tk.Event) -> None:
        if event.width <= 10 or event.height <= 10:
            return
        if (event.width, event.height) == self._last_canvas_size:
            return
        self._last_canvas_size = (event.width, event.height)

        if self._placeholder_text:
            self._draw_placeholder()
            return

        if self.original_image is not None:
            # If never drawn before, draw immediately; otherwise debounce rapid resizing
            if self._tk_image is None:
                self.redraw()
            else:
                self._cancel_timer()
                self._resize_timer = self.after(30, self.redraw)

    def _draw_placeholder(self) -> None:
        self.delete("all")
        if not self._placeholder_text:
            return
        w = self.winfo_width()
        h = self.winfo_height()
        if w > 10 and h > 10:
            self.create_text(
                w // 2,
                h // 2,
                text=self._placeholder_text,
                font=("Helvetica", 11, "italic"),
                fill="#888888",
                anchor=tk.CENTER,
            )

    def redraw(self, width: Optional[int] = None, height: Optional[int] = None) -> None:
        """Resize original image to fit current canvas size without altering aspect ratio."""
        self._resize_timer = None

        if self._placeholder_text:
            self._draw_placeholder()
            return

        if self.original_image is None:
            self.delete("all")
            return

        w = width if width is not None else self.winfo_width()
        h = height if height is not None else self.winfo_height()
        if w <= 10 or h <= 10:
            # Fallback to requested dimensions (e.g. In headless tests or withdrawn windows)
            w = width if width is not None else self.winfo_reqwidth()
            h = height if height is not None else self.winfo_reqheight()
            if w <= 10 or h <= 10:
                return

        pad = 12
        avail_w = max(1, w - 2 * pad)
        avail_h = max(1, h - 2 * pad)

        orig_w, orig_h = self.original_image.size
        if orig_w <= 0 or orig_h <= 0:
            return

        # Calculate scale factor preserving aspect ratio
        scale = min(avail_w / orig_w, avail_h / orig_h)
        new_w = max(1, int(orig_w * scale))
        new_h = max(1, int(orig_h * scale))

        # Scale image to fit
        resized = self.original_image.resize((new_w, new_h), Image.Resampling.LANCZOS)
        self._tk_image = ImageTk.PhotoImage(resized)

        self.delete("all")
        self.create_image(w // 2, h // 2, anchor=tk.CENTER, image=self._tk_image)


class PreviewTabs(ttk.Notebook):
    """Notebook containing Overview, Baseline, Noisewidth, and Module IV preview tabs."""

    def __init__(self, parent: tk.Widget):
        super().__init__(parent)
        self.images: Dict[str, Image.Image] = {}
        self.current_batch: Optional[UploadBatch] = None
        self.current_run_data: Optional[TestRunData] = None
        self._rendered_tabs: Set[str] = set()

        # Create Tab Frames
        self.overview_frame = ttk.Frame(self, padding="12 12 12 12")
        self.baseline_frame = ttk.Frame(self)
        self.noisewidth_frame = ttk.Frame(self)
        self.iv_frame = ttk.Frame(self)
        self.precure_frame = ttk.Frame(self)
        self.postcure_frame = ttk.Frame(self)

        self.add(self.overview_frame, text="  Overview & Summary  ")
        self.add(self.baseline_frame, text="  Baseline Plot  ")
        self.add(self.noisewidth_frame, text="  Noisewidth Plot  ")
        self.add(self.iv_frame, text="  Module IV Plot  ")
        self.add(self.precure_frame, text="  Precure Alignment  ")
        self.add(self.postcure_frame, text="  Postcure Alignment  ")

        # Create scaling canvas inside each plot frame
        self.baseline_canvas = ScalingImageCanvas(self.baseline_frame)
        self.baseline_canvas.pack(fill=tk.BOTH, expand=True)

        self.noisewidth_canvas = ScalingImageCanvas(self.noisewidth_frame)
        self.noisewidth_canvas.pack(fill=tk.BOTH, expand=True)

        self.iv_canvas = ScalingImageCanvas(self.iv_frame)
        self.iv_canvas.pack(fill=tk.BOTH, expand=True)

        self.precure_canvas = ScalingImageCanvas(self.precure_frame)
        self.precure_canvas.pack(fill=tk.BOTH, expand=True)

        self.postcure_canvas = ScalingImageCanvas(self.postcure_frame)
        self.postcure_canvas.pack(fill=tk.BOTH, expand=True)

        self._init_overview_tab()
        self.baseline_canvas.set_placeholder("No baseline data loaded.")
        self.noisewidth_canvas.set_placeholder("No noisewidth data loaded.")
        self.iv_canvas.set_placeholder("No module IV data loaded.")
        self.precure_canvas.set_placeholder("No precure alignment data loaded.")
        self.postcure_canvas.set_placeholder("No postcure alignment data loaded.")

        self.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    @property
    def figures(self) -> List[Any]:
        """Backward-compatible property exposing rendered plot image representations."""
        return list(self.images.values())

    def _init_overview_tab(self) -> None:
        """Initialize empty overview tab layout."""
        for child in self.overview_frame.winfo_children():
            child.destroy()

        self.tree = ttk.Treeview(self.overview_frame, columns=("property", "value"), show="headings", height=12)
        self.tree.heading("property", text="Property / File")
        self.tree.heading("value", text="Details")
        self.tree.column("property", width=220, anchor=tk.W)
        self.tree.column("value", width=550, anchor=tk.W)

        scrollbar = ttk.Scrollbar(self.overview_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.warnings_label = ttk.Label(
            self.overview_frame,
            text="Please select a test run directory to load and validate data.",
            font=("Helvetica", 10),
            foreground="#555555",
            wraplength=700,
        )
        self.warnings_label.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0))

    def _on_tab_changed(self, event: Optional[tk.Event] = None) -> None:
        """Trigger on-demand plot rendering and canvas redraw when user switches tabs."""
        def _deferred_handle() -> None:
            try:
                selected_tab = str(self.select())
            except Exception:
                return

            tab_mapping = {
                str(self.baseline_frame): ("baseline", self.baseline_canvas),
                str(self.noisewidth_frame): ("noisewidth", self.noisewidth_canvas),
                str(self.iv_frame): ("iv", self.iv_canvas),
                str(self.precure_frame): ("precure", self.precure_canvas),
                str(self.postcure_frame): ("postcure", self.postcure_canvas),
            }

            if selected_tab in tab_mapping:
                key, canvas = tab_mapping[selected_tab]
                if key not in self._rendered_tabs and self.current_batch:
                    self.render_tab(key)
                else:
                    canvas.redraw()

        self.after_idle(_deferred_handle)

    def render_tab(self, tab_key: str) -> Optional[Image.Image]:
        """Render a specific plot tab on-demand if not already rendered."""
        if tab_key in self.images:
            return self.images[tab_key]

        if not self.current_batch:
            return None

        img: Optional[Image.Image] = None

        if tab_key == "baseline":
            if self.current_batch.baseline is not None:
                self.baseline_canvas.set_placeholder("Rendering baseline plot...")
                self.update_idletasks()
                try:
                    fig_bl = self.current_batch.baseline.plot()
                    img = render_figure_to_image(fig_bl)
                    self.images["baseline"] = img
                    self._rendered_tabs.add("baseline")
                    self.baseline_canvas.set_image(img)
                except Exception as e:
                    self.baseline_canvas.set_placeholder(f"Failed to plot baseline: {e}")
            else:
                self.baseline_canvas.set_placeholder("No baseline matrices available to plot.")

        elif tab_key == "noisewidth":
            if self.current_batch.noisewidth is not None:
                self.noisewidth_canvas.set_placeholder("Rendering noisewidth plot...")
                self.update_idletasks()
                try:
                    fig_nw = self.current_batch.noisewidth.plot()
                    img = render_figure_to_image(fig_nw)
                    self.images["noisewidth"] = img
                    self._rendered_tabs.add("noisewidth")
                    self.noisewidth_canvas.set_image(img)
                except Exception as e:
                    self.noisewidth_canvas.set_placeholder(f"Failed to plot noisewidth: {e}")
            else:
                self.noisewidth_canvas.set_placeholder("No noisewidth matrices available to plot.")

        elif tab_key == "iv":
            iv_model = self.current_batch.module_iv or (self.current_batch.module_ivs[0] if self.current_batch.module_ivs else None)
            if iv_model is not None:
                self.iv_canvas.set_placeholder("Rendering module IV plot...")
                self.update_idletasks()
                try:
                    fig_iv = iv_model.plot()
                    img = render_figure_to_image(fig_iv)
                    self.images["iv"] = img
                    self._rendered_tabs.add("iv")
                    self.iv_canvas.set_image(img)
                except Exception as e:
                    self.iv_canvas.set_placeholder(f"Failed to plot module IV: {e}")
            else:
                self.iv_canvas.set_placeholder("No IV curve data available to plot.")

        elif tab_key == "precure":
            if self.current_batch.precure_alignment is not None:
                self.precure_canvas.set_placeholder("Rendering precure alignment plot...")
                self.update_idletasks()
                try:
                    fig_pre = self.current_batch.precure_alignment.plot()
                    img = render_figure_to_image(fig_pre)
                    self.images["precure"] = img
                    self._rendered_tabs.add("precure")
                    self.precure_canvas.set_image(img)
                except Exception as e:
                    self.precure_canvas.set_placeholder(f"Failed to plot precure alignment: {e}")
            else:
                self.precure_canvas.set_placeholder("No precure alignment data available to plot.")

        elif tab_key == "postcure":
            if self.current_batch.postcure_alignment is not None:
                self.postcure_canvas.set_placeholder("Rendering postcure alignment plot...")
                self.update_idletasks()
                try:
                    fig_post = self.current_batch.postcure_alignment.plot()
                    img = render_figure_to_image(fig_post)
                    self.images["postcure"] = img
                    self._rendered_tabs.add("postcure")
                    self.postcure_canvas.set_image(img)
                except Exception as e:
                    self.postcure_canvas.set_placeholder(f"Failed to plot postcure alignment: {e}")
            else:
                self.postcure_canvas.set_placeholder("No postcure alignment data available to plot.")

        return img

    def render_all_plots(self) -> None:
        """Render all available plot tabs on demand."""
        for key in ("baseline", "noisewidth", "iv", "precure", "postcure"):
            self.render_tab(key)

    def clear(self) -> None:
        """Clear all loaded figures and reset tabs to empty state."""
        self.images.clear()
        self._rendered_tabs.clear()
        self.current_batch = None
        self.current_run_data = None
        self._init_overview_tab()
        self.baseline_canvas.set_placeholder("No baseline data loaded.")
        self.noisewidth_canvas.set_placeholder("No noisewidth data loaded.")
        self.iv_canvas.set_placeholder("No module IV data loaded.")
        self.precure_canvas.set_placeholder("No precure alignment data loaded.")
        self.postcure_canvas.set_placeholder("No postcure alignment data loaded.")

    def _populate_overview_tree(
        self,
        run_data: TestRunData,
        total_batch: UploadBatch,
        selected_keys: Optional[Set[str]] = None,
        active_batch: Optional[UploadBatch] = None,
    ) -> None:
        """Populate overview tree table with test discovery, counts, and inclusion statuses."""
        for item in self.tree.get_children():
            self.tree.delete(item)

        meta = run_data.metadata
        self.tree.insert("", tk.END, values=("Run Directory", str(run_data.directory)))
        self.tree.insert("", tk.END, values=("Module Serial", meta.module or "Unknown"))
        self.tree.insert("", tk.END, values=("Measurement Date", str(meta.measurement_date or "Unknown")))
        bias_str = f"{meta.bias_volts} V" if meta.bias_volts is not None else "Not specified"
        self.tree.insert("", tk.END, values=("Bias Voltage", bias_str))

        def _status_suffix(key: str, available: bool) -> str:
            if not available:
                return "Not found"
            if selected_keys is None or key in selected_keys:
                return "INCLUDED"
            return "EXCLUDED"

        # Baseline files
        bl_avail = total_batch.baseline is not None
        bl_count = len(run_data.baseline_matrices)
        bl_pos = ", ".join(f"pos_{p}" for p in sorted(run_data.baseline_matrices.keys())) or "None"
        bl_tag = _status_suffix("baseline", bl_avail)
        bl_text = f"{bl_count} loaded ({bl_pos})  [{bl_tag}]" if bl_avail else "Not found"
        self.tree.insert("", tk.END, values=("Baseline Matrices", bl_text))

        # Noisewidth files
        nw_avail = total_batch.noisewidth is not None
        nw_count = len(run_data.noisewidth_matrices)
        nw_pos = ", ".join(f"pos_{p}" for p in sorted(run_data.noisewidth_matrices.keys())) or "None"
        nw_tag = _status_suffix("noisewidth", nw_avail)
        nw_text = f"{nw_count} loaded ({nw_pos})  [{nw_tag}]" if nw_avail else "Not found"
        self.tree.insert("", tk.END, values=("Noisewidth Matrices", nw_text))

        # IV File
        iv_avail = total_batch.module_iv is not None or len(total_batch.module_ivs) > 0
        iv_tag = _status_suffix("module_iv", iv_avail)
        if run_data.iv_data:
            num_pts = len(run_data.iv_data["voltage"])
            k_stat = "with k_factor" if run_data.iv_data.get("k_factor") is not None else "without k_factor"
            self.tree.insert("", tk.END, values=("Module IV Curve", f"{num_pts} points ({k_stat})  [{iv_tag}]"))
        else:
            self.tree.insert("", tk.END, values=("Module IV Curve", "Not found"))

        # Alignment surveys
        pre_avail = total_batch.precure_alignment is not None
        pre_tag = _status_suffix("precure_alignment", pre_avail)
        if "precure" in run_data.survey_data:
            pre_s = run_data.survey_data["precure"]
            pre_pos = ", ".join(f"pos_{p}" for p in sorted(pre_s.positions.keys())) or "None"
            self.tree.insert("", tk.END, values=("Precure Alignment", f"Loaded ({pre_pos})  [{pre_tag}]"))
        else:
            self.tree.insert("", tk.END, values=("Precure Alignment", "Not found"))

        post_avail = total_batch.postcure_alignment is not None
        post_tag = _status_suffix("postcure_alignment", post_avail)
        if "postcure" in run_data.survey_data:
            post_s = run_data.survey_data["postcure"]
            post_pos = ", ".join(f"pos_{p}" for p in sorted(post_s.positions.keys())) or "None"
            self.tree.insert("", tk.END, values=("Postcure Alignment", f"Loaded ({post_pos})  [{post_tag}]"))
        else:
            self.tree.insert("", tk.END, values=("Postcure Alignment", "Not found"))

        active_count = active_batch.total_count if active_batch is not None else total_batch.total_count
        if active_count == total_batch.total_count:
            summary_str = f"{active_count} record(s) staged"
        else:
            summary_str = f"{active_count} record(s) selected for upload (out of {total_batch.total_count} staged)"
        self.tree.insert("", tk.END, values=("Total Upload Items", summary_str))

    def update_selection_summary(
        self,
        run_data: TestRunData,
        total_batch: UploadBatch,
        selected_keys: Set[str],
        active_batch: UploadBatch,
    ) -> None:
        """Update overview tree table with updated test selection without re-rendering plots."""
        self._populate_overview_tree(run_data, total_batch, selected_keys, active_batch)

    def set_test_run(
        self,
        run_data: TestRunData,
        batch: UploadBatch,
        selected_keys: Optional[Set[str]] = None,
        active_batch: Optional[UploadBatch] = None,
    ) -> None:
        """Populate overview and prepare plots for lazy on-demand rendering."""
        self.clear()
        self.current_run_data = run_data
        self.current_batch = batch

        # 1. Update Overview Tree
        self._populate_overview_tree(run_data, batch, selected_keys, active_batch)

        # Warnings label
        if run_data.warnings:
            warn_text = "⚠️ Warnings:\n" + "\n".join(f"• {w}" for w in run_data.warnings)
            self.warnings_label.config(text=warn_text, foreground="#d9534f")
        else:
            self.warnings_label.config(text="✓ All expected data files discovered and successfully validated.", foreground="#3c763d")

        # Set placeholders for tabs
        if batch.baseline is not None:
            self.baseline_canvas.set_placeholder("Switch to this tab to display Baseline plot.")
        else:
            self.baseline_canvas.set_placeholder("No baseline matrices available to plot.")

        if batch.noisewidth is not None:
            self.noisewidth_canvas.set_placeholder("Switch to this tab to display Noisewidth plot.")
        else:
            self.noisewidth_canvas.set_placeholder("No noisewidth matrices available to plot.")

        iv_model = batch.module_iv or (batch.module_ivs[0] if batch.module_ivs else None)
        if iv_model is not None:
            self.iv_canvas.set_placeholder("Switch to this tab to display Module IV plot.")
        else:
            self.iv_canvas.set_placeholder("No IV curve data available to plot.")

        if batch.precure_alignment is not None:
            self.precure_canvas.set_placeholder("Switch to this tab to display Precure Alignment plot.")
        else:
            self.precure_canvas.set_placeholder("No precure alignment data available to plot.")

        if batch.postcure_alignment is not None:
            self.postcure_canvas.set_placeholder("Switch to this tab to display Postcure Alignment plot.")
        else:
            self.postcure_canvas.set_placeholder("No postcure alignment data available to plot.")

        # If currently active tab is one of the plot tabs, render it immediately
        try:
            selected_tab = str(self.select())
            for frame, key in (
                (self.baseline_frame, "baseline"),
                (self.noisewidth_frame, "noisewidth"),
                (self.iv_frame, "iv"),
                (self.precure_frame, "precure"),
                (self.postcure_frame, "postcure"),
            ):
                if str(frame) == selected_tab:
                    self.render_tab(key)
                    break
        except Exception:
            pass
