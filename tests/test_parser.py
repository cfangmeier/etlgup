from pathlib import Path
import pytest
from etlgup.parser import (
    coerce_rotation,
    discover_and_parse_directory,
    extract_metadata_from_path,
    parse_iv_csv,
    parse_survey_file,
    parse_yaml_matrix,
)

SAMPLE_DIR = Path("/home/caleb/Downloads/MP40229/2026-09-15-12-03-51_AFTER-BL-100V")


def test_extract_metadata_from_path():
    meta = extract_metadata_from_path(SAMPLE_DIR)
    assert meta.module == "40229"
    assert meta.bias_volts == 100.0
    assert meta.measurement_date is not None
    assert meta.measurement_date.year == 2026
    assert meta.measurement_date.month == 9
    assert meta.measurement_date.day == 15
    assert meta.measurement_date.hour == 12
    assert meta.measurement_date.minute == 3
    assert meta.measurement_date.second == 51


def test_parse_yaml_matrix():
    bl_file = SAMPLE_DIR / "module_40229_etroc_0_baseline_auto.yaml"
    matrix = parse_yaml_matrix(bl_file)
    assert len(matrix) == 16
    for row in matrix:
        assert len(row) == 16
        for val in row:
            assert isinstance(val, int)


def test_parse_iv_csv():
    import json
    import math
    csv_file = SAMPLE_DIR / "IV_Curve_40229_2026-09-15-11-59-06.csv"
    data = parse_iv_csv(csv_file)
    assert "voltage" in data
    assert "current" in data
    assert "k_factor" in data
    assert len(data["voltage"]) > 10
    assert len(data["voltage"]) == len(data["current"])
    assert len(data["voltage"]) == len(data["k_factor"])
    # First k_factor element was NaN in raw CSV, must now be converted to 0.0
    assert data["k_factor"][0] == 0.0
    for key in ("voltage", "current", "k_factor"):
        for val in data[key]:
            assert not math.isnan(val)
    # Verify strict JSON compliance
    json_str = json.dumps(data, allow_nan=False)
    assert len(json_str) > 0


def test_coerce_rotation():
    assert coerce_rotation(0.0) == 0.0
    assert coerce_rotation(180.0) == 180.0
    assert coerce_rotation(-180.0) == 180.0
    assert coerce_rotation(540.0) == 180.0
    assert coerce_rotation(-540.0) == 180.0
    assert coerce_rotation(360.0) == 0.0
    assert coerce_rotation(-360.0) == 0.0
    assert coerce_rotation(90.0) == 90.0
    assert coerce_rotation(-90.0) == -90.0
    # Precise test values from sample surveys
    assert abs(coerce_rotation(180.441883) - (-179.558117)) < 1e-6
    assert abs(coerce_rotation(-360.022797) - (-0.022797)) < 1e-6
    assert abs(coerce_rotation(180.253102) - (-179.746898)) < 1e-6
    assert abs(coerce_rotation(-359.907189) - 0.092811) < 1e-6
    # Verify strict interval (-180, 180]
    for angle in (-720, -540, -360.02, -180.01, -180.0, -179.99, -1, 0, 1, 179.99, 180.0, 180.01, 360, 720):
        c = coerce_rotation(angle)
        assert -180.0 < c <= 180.0


def test_parse_survey_file():
    pre_file = SAMPLE_DIR / "H4_ETROC_Survey_Precure_2026-09-11--16-39-13.txt"
    pre_data = parse_survey_file(pre_file)
    assert pre_data.stage == "Precure"
    assert pre_data.timestamp is not None
    assert pre_data.timestamp.year == 2026
    assert pre_data.timestamp.month == 9
    assert pre_data.timestamp.day == 11
    assert pre_data.timestamp.hour == 16
    assert pre_data.timestamp.minute == 39
    assert pre_data.timestamp.second == 13
    assert set(pre_data.positions.keys()) == {0, 1, 2, 3}

    for pos, pdata in pre_data.positions.items():
        assert len(pdata.target) == 4
        assert len(pdata.actual) == 4
        assert len(pdata.delta) == 4
        # Target, actual, delta rotations coerced to (-180, 180]
        assert -180.0 < pdata.target[3] <= 180.0
        assert -180.0 < pdata.actual[3] <= 180.0
        assert -180.0 < pdata.delta[3] <= 180.0

    post_file = SAMPLE_DIR / "H4_ETROC_Survey_Postcure_2026-09-11--17-46-48.txt"
    post_data = parse_survey_file(post_file)
    assert post_data.stage == "Postcure"
    assert post_data.timestamp is not None
    assert post_data.timestamp.hour == 17
    assert set(post_data.positions.keys()) == {0, 1, 2, 3}


def test_discover_and_parse_directory():
    run_data = discover_and_parse_directory(SAMPLE_DIR)
    assert run_data.metadata.module == "40229"
    assert run_data.metadata.bias_volts == 100.0
    assert len(run_data.baseline_files) == 4
    assert len(run_data.noisewidth_files) == 4
    assert run_data.iv_file is not None
    assert len(run_data.survey_files) == 2
    assert set(run_data.survey_files.keys()) == {"precure", "postcure"}
    assert len(run_data.survey_data) == 2
    assert set(run_data.baseline_matrices.keys()) == {0, 1, 2, 3}
    assert set(run_data.noisewidth_matrices.keys()) == {0, 1, 2, 3}
    assert run_data.iv_data is not None
    # No missing chip warnings for this folder
    assert not any("Missing baseline" in w for w in run_data.warnings)
