from pathlib import Path
import pytest
from etlgup.parser import discover_and_parse_directory
from etlgup.models import (
    build_upload_batch,
    create_baseline_model,
    create_noisewidth_model,
    create_module_iv_model,
    create_module_iv_models,
    create_subassembly_alignment_model,
)

SAMPLE_DIR = Path("/home/caleb/Downloads/MP40229/2026-09-15-12-03-51_AFTER-BL-100V")


def test_build_upload_batch():
    run_data = discover_and_parse_directory(SAMPLE_DIR)
    batch = build_upload_batch(
        run_data=run_data,
        location="BU",
        user_created="hayden",
    )
    assert batch.baseline is not None
    assert batch.noisewidth is not None
    assert batch.module_iv is not None
    assert len(batch.module_ivs) == 1
    assert batch.precure_alignment is not None
    assert batch.postcure_alignment is not None
    assert len(batch.subassembly_alignments) == 2
    assert batch.total_count == 5

    # Verify single IV model component_pos defaults to 0
    assert batch.module_iv.component_pos == 0

    # Verify subassembly alignments have expected names and versions
    assert batch.precure_alignment.name == "subassembly alignment"
    assert batch.precure_alignment.version == "v1"
    assert batch.postcure_alignment.name == "subassembly alignment"
    assert batch.postcure_alignment.version == "v1"

    # Verify all models can generate plots
    import matplotlib.pyplot as plt

    fig_bl = batch.baseline.plot()
    assert fig_bl is not None
    plt.close(fig_bl)

    fig_nw = batch.noisewidth.plot()
    assert fig_nw is not None
    plt.close(fig_nw)

    fig_iv = batch.module_iv.plot()
    assert fig_iv is not None
    plt.close(fig_iv)

    fig_pre = batch.precure_alignment.plot()
    assert fig_pre is not None
    plt.close(fig_pre)

    fig_post = batch.postcure_alignment.plot()
    assert fig_post is not None
    plt.close(fig_post)


def test_create_subassembly_alignment_model():
    run_data = discover_and_parse_directory(SAMPLE_DIR)
    pre_survey = run_data.survey_data["precure"]
    model = create_subassembly_alignment_model(
        survey=pre_survey,
        location="BU",
        user_created="caleb",
        module="40229",
    )
    assert model is not None
    assert model.module == "40229"
    assert model.location == "BU"
    assert model.name == "subassembly alignment"
    assert model.position_0 is not None
    assert model.position_1 is not None
    assert model.position_2 is not None
    assert model.position_3 is not None
    # Check that rotation in target and delta are within (-180, 180]
    for p in (model.position_0, model.position_1, model.position_2, model.position_3):
        assert -180.0 < p.target[3] <= 180.0
        assert -180.0 < p.actual[3] <= 180.0
        assert -180.0 < p.delta[3] <= 180.0


def test_create_module_iv_models_explicit_positions():
    run_data = discover_and_parse_directory(SAMPLE_DIR)
    # Default is 1 model at pos 0
    single = create_module_iv_models(run_data, location="BU", user_created="user")
    assert len(single) == 1
    assert single[0].component_pos == 0

    # Explicit positions
    explicit = create_module_iv_models(run_data, location="BU", user_created="user", positions=(0, 1))
    assert len(explicit) == 2
    assert [m.component_pos for m in explicit] == [0, 1]


def test_upload_batch_filter_tests():
    run_data = discover_and_parse_directory(SAMPLE_DIR)
    batch = build_upload_batch(run_data=run_data, location="BU", user_created="caleb")
    assert batch.total_count == 5

    # 1. Filter to only baseline
    b_bl = batch.filter_tests(
        include_baseline=True,
        include_noisewidth=False,
        include_module_iv=False,
        include_precure_alignment=False,
        include_postcure_alignment=False,
    )
    assert b_bl.total_count == 1
    assert b_bl.baseline is not None
    assert b_bl.noisewidth is None
    assert b_bl.module_iv is None
    assert b_bl.precure_alignment is None
    assert b_bl.postcure_alignment is None
    assert len(b_bl.all_models()) == 1

    # 2. Filter to baseline and module IV
    b_bl_iv = batch.filter_tests(
        include_baseline=True,
        include_noisewidth=False,
        include_module_iv=True,
        include_precure_alignment=False,
        include_postcure_alignment=False,
    )
    assert b_bl_iv.total_count == 2
    assert b_bl_iv.baseline is not None
    assert b_bl_iv.module_iv is not None
    assert len(b_bl_iv.all_models()) == 2

    # 3. Filter to both alignments
    b_align = batch.filter_tests(
        include_baseline=False,
        include_noisewidth=False,
        include_module_iv=False,
        include_precure_alignment=True,
        include_postcure_alignment=True,
    )
    assert b_align.total_count == 2
    assert b_align.precure_alignment is not None
    assert b_align.postcure_alignment is not None
    assert len(b_align.all_models()) == 2

    # 4. Filter with everything deselected
    b_none = batch.filter_tests(
        include_baseline=False,
        include_noisewidth=False,
        include_module_iv=False,
        include_precure_alignment=False,
        include_postcure_alignment=False,
    )
    assert b_none.total_count == 0
    assert len(b_none.all_models()) == 0


def test_upload_batch_filter_by_keys():
    run_data = discover_and_parse_directory(SAMPLE_DIR)
    batch = build_upload_batch(run_data=run_data, location="BU", user_created="caleb")

    # Select by keys
    filtered = batch.filter_by_keys(["noisewidth", "precure_alignment"])
    assert filtered.total_count == 2
    assert filtered.noisewidth is not None
    assert filtered.precure_alignment is not None
    assert filtered.baseline is None
    assert filtered.module_iv is None
    assert filtered.postcure_alignment is None

    # Empty keys
    empty_filtered = batch.filter_by_keys([])
    assert empty_filtered.total_count == 0
    assert len(empty_filtered.all_models()) == 0
