from pathlib import Path
import time
import tkinter as tk
import pytest

from etlgup.config import AppConfig
from etlgup.gui.app import ETLGupApp
from etlgup.gui.settings_dialog import SettingsDialog

SAMPLE_DIR = Path("/home/caleb/Downloads/MP40229/2026-09-15-12-03-51_AFTER-BL-100V")




def test_gui_initialization(tk_root):
    app = ETLGupApp(tk_root)
    assert app.root == tk_root
    assert app.current_dir is None
    assert app.current_batch is None


def test_gui_load_directory(tk_root):
    app = ETLGupApp(tk_root)
    app._load_directory(SAMPLE_DIR)

    # Wait for background thread to complete
    max_wait = 10.0
    start = time.time()
    while app.is_busy and (time.time() - start < max_wait):
        tk_root.update()
        time.sleep(0.05)

    assert not app.is_busy
    assert app.current_run_data is not None
    assert app.current_batch is not None
    assert app.current_batch.total_count == 5
    assert app.current_batch.module_iv is not None
    assert len(app.current_batch.module_ivs) == 1
    assert app.current_batch.precure_alignment is not None
    assert app.current_batch.postcure_alignment is not None

    # Verify metadata fields populated
    assert app.meta_module_var.get() == "40229"
    assert "2026-09-15 12:03:51" in app.meta_date_var.get()
    assert app.meta_bias_var.get() == "100.0"

    # Verify tabs are loaded lazily: initially 0 plots rendered while overview is displayed
    assert len(app.tabs.images) == 0

    # Verify rendering on-demand
    app.tabs.render_all_plots()
    assert len(app.tabs.images) >= 5
    assert len(app.tabs.figures) >= 5
    assert "precure" in app.tabs.images
    assert "postcure" in app.tabs.images
    for name, img in app.tabs.images.items():
        assert img is not None
        assert img.width > 0 and img.height > 0


def test_gui_apply_metadata(tk_root):
    app = ETLGupApp(tk_root)
    app._load_directory(SAMPLE_DIR)

    # Wait for load
    start = time.time()
    while app.is_busy and (time.time() - start < 10.0):
        tk_root.update()
        time.sleep(0.05)

    # Change module serial number
    app.meta_module_var.set("99999")
    app._apply_metadata()
    tk_root.update()

    assert app.current_batch.baseline.module == "99999"
    assert app.current_batch.noisewidth.module == "99999"
    assert app.current_batch.module_ivs[0].module == "99999"
    assert app.current_batch.precure_alignment.module == "99999"
    assert app.current_batch.postcure_alignment.module == "99999"


def test_settings_dialog(tk_root):
    cfg = AppConfig(location="BU", user_created="orig_user", api_token="orig_tok")
    saved_cfg = None

    def on_save(c):
        nonlocal saved_cfg
        saved_cfg = c

    dialog = SettingsDialog(tk_root, cfg, on_save=on_save)
    dialog.user_var.set("new_operator")
    dialog.loc_var.set("FNAL")
    dialog.token_var.set("new_tok_xyz")
    dialog.prod_var.set(True)
    dialog._save()

    assert saved_cfg is not None
    assert saved_cfg.user_created == "new_operator"
    assert saved_cfg.location == "FNAL"
    assert saved_cfg.api_token == "new_tok_xyz"
    assert saved_cfg.prod is True


def test_render_figure_to_png_image():
    import matplotlib.pyplot as plt
    from PIL import Image
    from etlgup.gui.preview_tabs import render_figure_to_png_image

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot([1, 2], [3, 4])
    fignum = fig.number

    img = render_figure_to_png_image(fig)
    assert isinstance(img, Image.Image)
    assert img.width > 0 and img.height > 0
    # Figure should be closed immediately
    assert not plt.fignum_exists(fignum)


def test_scaling_image_canvas_aspect_ratio(tk_root):
    from PIL import Image
    from etlgup.gui.preview_tabs import ScalingImageCanvas

    frame = tk.Frame(tk_root, width=500, height=500)
    frame.pack()
    canvas = ScalingImageCanvas(frame)
    canvas.pack(fill=tk.BOTH, expand=True)

    # Image with 2.0 aspect ratio (1000x500)
    img = Image.new("RGB", (1000, 500), color="blue")
    canvas.set_image(img)

    # Force geometry to wide 400x200
    canvas.config(width=400, height=200)
    canvas.redraw(width=400, height=200)

    assert canvas._tk_image is not None
    # Aspect ratio should remain 2.0 within rounding tolerances
    ratio = canvas._tk_image.width() / canvas._tk_image.height()
    assert abs(ratio - 2.0) < 0.05
    # Should fit inside available width and height
    assert canvas._tk_image.width() <= 400
    assert canvas._tk_image.height() <= 200

    # Force geometry to tall 200x400
    canvas.config(width=200, height=400)
    canvas.redraw(width=200, height=400)

    assert canvas._tk_image is not None
    ratio_tall = canvas._tk_image.width() / canvas._tk_image.height()
    assert abs(ratio_tall - 2.0) < 0.05
    assert canvas._tk_image.width() <= 200
    assert canvas._tk_image.height() <= 400


def test_gui_test_selection_initial_state(tk_root):
    app = ETLGupApp(tk_root)
    # Before loading, all checkboxes and action buttons should be disabled
    for key, cb in app.test_checkboxes.items():
        assert str(cb.cget("state")) == "disabled"
    assert str(app.select_all_btn.cget("state")) == "disabled"
    assert str(app.deselect_all_btn.cget("state")) == "disabled"
    assert "No data loaded" in app.selection_summary_lbl.cget("text")


def test_gui_test_selection_loaded_and_toggle(tk_root):
    app = ETLGupApp(tk_root)
    app._load_directory(SAMPLE_DIR)

    # Wait for load
    start = time.time()
    while app.is_busy and (time.time() - start < 10.0):
        tk_root.update()
        time.sleep(0.05)

    assert not app.is_busy
    # All 5 tests are present in SAMPLE_DIR and should be enabled and checked
    for key, cb in app.test_checkboxes.items():
        assert str(cb.cget("state")) == "normal"
        assert app.test_vars[key].get() is True

    assert app._get_selected_keys() == {
        "baseline",
        "noisewidth",
        "module_iv",
        "precure_alignment",
        "postcure_alignment",
    }
    assert app._get_active_batch().total_count == 5
    assert "5 of 5 tests selected (5 records)" in app.selection_summary_lbl.cget("text")

    # 1. Deselect Module IV
    app.test_vars["module_iv"].set(False)
    app._on_test_selection_changed()
    tk_root.update()

    selected = app._get_selected_keys()
    assert "module_iv" not in selected
    assert len(selected) == 4
    active_b = app._get_active_batch()
    assert active_b.total_count == 4
    assert active_b.module_iv is None
    assert "4 of 5 tests selected (4 records)" in app.selection_summary_lbl.cget("text")

    # 2. Deselect all
    app._deselect_all_tests()
    tk_root.update()
    assert len(app._get_selected_keys()) == 0
    assert app._get_active_batch().total_count == 0
    assert "0 of 5 tests selected (0 records)" in app.selection_summary_lbl.cget("text")
    assert "No tests selected for upload" in app.status_label.cget("text")

    # 3. Select all
    app._select_all_tests()
    tk_root.update()
    assert len(app._get_selected_keys()) == 5
    assert app._get_active_batch().total_count == 5
    assert "5 of 5 tests selected (5 records)" in app.selection_summary_lbl.cget("text")


def test_gui_dry_run_with_test_selection(tk_root):
    app = ETLGupApp(tk_root)
    app._load_directory(SAMPLE_DIR)

    start = time.time()
    while app.is_busy and (time.time() - start < 10.0):
        tk_root.update()
        time.sleep(0.05)

    # Deselect all except baseline and module_iv
    app._deselect_all_tests()
    app.test_vars["baseline"].set(True)
    app.test_vars["module_iv"].set(True)
    app._on_test_selection_changed()
    tk_root.update()

    active_b = app._get_active_batch()
    assert active_b.total_count == 2

    # Execute dry run directly on active batch
    res = app.upload_service.execute_dry_run(active_b)
    assert res.success is True
    assert res.count == 2
    assert len(res.details["test_payload"]) == 2


def test_gui_lazy_tab_switching(tk_root):
    app = ETLGupApp(tk_root)
    app._load_directory(SAMPLE_DIR)

    start = time.time()
    while app.is_busy and (time.time() - start < 10.0):
        tk_root.update()
        time.sleep(0.05)

    assert not app.is_busy
    # Initially 0 plots rendered
    assert len(app.tabs.images) == 0

    # Select IV tab
    app.tabs.select(app.tabs.iv_frame)
    app.tabs._on_tab_changed()
    tk_root.update_idletasks()

    # Only module IV should now be rendered
    assert "iv" in app.tabs.images
    assert len(app.tabs.images) == 1
    assert app.tabs.iv_canvas.original_image is not None

    # Select Precure alignment tab
    app.tabs.select(app.tabs.precure_frame)
    app.tabs._on_tab_changed()
    tk_root.update_idletasks()

    assert "precure" in app.tabs.images
    assert len(app.tabs.images) == 2
