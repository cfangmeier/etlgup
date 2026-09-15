"""Test directory discovery and file parsing utilities."""

from dataclasses import dataclass, field
import datetime
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional
import csv
import math
import pytz
import yaml


@dataclass
class DirectoryMetadata:
    module: Optional[str] = None
    measurement_date: Optional[datetime.datetime] = None
    bias_volts: Optional[float] = None


@dataclass
class SurveyPositionData:
    target: List[float]  # [x, y, z, rot]
    actual: List[float]  # [x, y, z, rot]
    delta: List[float]   # [dx, dy, dz, drot]


@dataclass
class SurveyData:
    stage: str  # "Precure" or "Postcure"
    file_path: Path
    timestamp: Optional[datetime.datetime] = None
    positions: Dict[int, SurveyPositionData] = field(default_factory=dict)


@dataclass
class TestRunData:
    directory: Path
    metadata: DirectoryMetadata
    baseline_files: Dict[int, Path] = field(default_factory=dict)
    noisewidth_files: Dict[int, Path] = field(default_factory=dict)
    iv_file: Optional[Path] = None
    survey_files: Dict[str, Path] = field(default_factory=dict)
    baseline_matrices: Dict[int, List[List[int]]] = field(default_factory=dict)
    noisewidth_matrices: Dict[int, List[List[int]]] = field(default_factory=dict)
    iv_data: Optional[Dict[str, List[float]]] = None
    survey_data: Dict[str, SurveyData] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


def extract_metadata_from_path(dir_path: Path) -> DirectoryMetadata:
    """Extract metadata (module, date, bias voltage) from directory and parent path names."""
    dir_name = dir_path.name
    full_str = str(dir_path.resolve())
    
    # 1. Module ID: look for MPxxxxx or module_xxxxx or from folder / parent folder
    module: Optional[str] = None
    mod_match = re.search(r'(?:MP|module[_-]?)([0-9A-Za-z]+)', full_str, re.IGNORECASE)
    if mod_match:
        module = mod_match.group(1)
        
    # 2. Measurement Date: format YYYY-MM-DD-HH-MM-SS or YYYY-MM-DD_HH-MM-SS
    meas_date: Optional[datetime.datetime] = None
    date_match = re.search(r'(\d{4})-(\d{2})-(\d{2})[-_](\d{2})[-_](\d{2})[-_](\d{2})', dir_name)
    if date_match:
        y, m, d, hh, mm, ss = map(int, date_match.groups())
        meas_date = datetime.datetime(y, m, d, hh, mm, ss, tzinfo=pytz.utc)
    else:
        # Fallback to dir modification time
        try:
            mtime = os.path.getmtime(dir_path)
            meas_date = datetime.datetime.fromtimestamp(mtime, tz=pytz.utc)
        except Exception:
            meas_date = datetime.datetime.now(pytz.utc)

    # 3. Bias Voltage: e.g. 100V, -100V, BL-100V
    bias_volts: Optional[float] = None
    bias_match = re.search(r'(?:[-_]|BL-)(\d+(?:\.\d+)?)V(?:\b|_|$)', dir_name, re.IGNORECASE)
    if bias_match:
        bias_volts = float(bias_match.group(1))
        
    return DirectoryMetadata(module=module, measurement_date=meas_date, bias_volts=bias_volts)


def parse_yaml_matrix(file_path: Path) -> List[List[int]]:
    """Parse a 16x16 YAML matrix of baseline or noisewidth values into integers."""
    with open(file_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, list):
        raise ValueError(f"Expected list of rows in {file_path}, got {type(data)}")
    
    matrix: List[List[int]] = []
    for row_idx, row in enumerate(data):
        if not isinstance(row, list):
            raise ValueError(f"Row {row_idx} in {file_path} is not a list")
        matrix.append([int(round(float(val))) for val in row])
        
    if len(matrix) != 16 or any(len(r) != 16 for r in matrix):
        raise ValueError(f"Matrix in {file_path} is {len(matrix)}x{[len(r) for r in matrix[:1]]}, expected 16x16")
    return matrix


def parse_iv_csv(file_path: Path) -> Dict[str, List[float]]:
    """Parse a Module IV curve CSV file containing voltage, current, and k_factor rows."""
    with open(file_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        rows = [row for row in reader if row and any(cell.strip() for cell in row)]
        
    if len(rows) < 2:
        raise ValueError(f"IV Curve CSV {file_path} must contain at least 2 rows (voltage, current)")
        
    def _parse_row(row_cells: List[str]) -> List[float]:
        parsed: List[float] = []
        for c in row_cells:
            val_str = c.strip()
            if not val_str or val_str.lower() == "nan":
                parsed.append(0.0)
            else:
                try:
                    val = float(val_str)
                    parsed.append(0.0 if math.isnan(val) else val)
                except ValueError:
                    parsed.append(0.0)
        return parsed
        
    voltage = _parse_row(rows[0])
    current = _parse_row(rows[1])
    k_factor = _parse_row(rows[2]) if len(rows) >= 3 else None
    
    if len(voltage) != len(current):
        raise ValueError(f"Voltage length ({len(voltage)}) does not match current length ({len(current)})")
    if k_factor is not None and len(k_factor) != len(voltage):
        raise ValueError(f"k_factor length ({len(k_factor)}) does not match voltage length ({len(voltage)})")
        
    return {
        "voltage": voltage,
        "current": current,
        "k_factor": k_factor,
    }


def coerce_rotation(angle_deg: float) -> float:
    """Coerce rotation angle in degrees to the half-open interval (-180, 180]."""
    res = 180.0 - (180.0 - angle_deg) % 360.0
    res = round(res, 9)
    if res <= -180.0 or res > 180.0:
        res = 180.0
    return res


def parse_survey_file(file_path: Path) -> SurveyData:
    """Parse an H4 ETROC survey text file (Precure or Postcure).

    Extracts module positions 0..3, coordinates in mm, coerces all rotations to (-180, 180],
    and extracts timestamp.
    """
    stage_match = re.search(r'(Precure|Postcure)', file_path.name, re.IGNORECASE)
    stage = stage_match.group(1).capitalize() if stage_match else "Survey"

    # 1. Parse timestamp from filename or content
    timestamp: Optional[datetime.datetime] = None
    fn_match = re.search(r'(\d{4})-(\d{2})-(\d{2})[-_]+(\d{2})[-_]+(\d{2})[-_]+(\d{2})', file_path.name)
    if fn_match:
        y, mo, d, h, mi, s = map(int, fn_match.groups())
        timestamp = datetime.datetime(y, mo, d, h, mi, s, tzinfo=pytz.utc)

    positions: Dict[int, SurveyPositionData] = {}
    current_pos: Optional[int] = None
    curr_target: Optional[List[float]] = None
    curr_actual: Optional[List[float]] = None
    curr_delta: Optional[List[float]] = None

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line_str = line.strip()
            if not line_str:
                continue

            # Check timestamp from file if not found from filename
            if timestamp is None:
                cm = re.search(r'(\d{2})/(\d{2})/(\d{4})\s+(\d{1,2}):(\d{2}):(\d{2})\s*(AM|PM)', line_str, re.IGNORECASE)
                if cm:
                    d, mo, y, h, mi, s = map(int, cm.groups()[:6])
                    ampm = cm.group(7).upper()
                    if ampm == "PM" and h < 12:
                        h += 12
                    elif ampm == "AM" and h == 12:
                        h = 0
                    timestamp = datetime.datetime(y, mo, d, h, mi, s, tzinfo=pytz.utc)

            pos_match = re.search(r'ETROC\s*([0-3])', line_str, re.IGNORECASE)
            if pos_match:
                if current_pos is not None and curr_target and curr_actual and curr_delta:
                    positions[current_pos] = SurveyPositionData(
                        target=curr_target, actual=curr_actual, delta=curr_delta
                    )
                current_pos = int(pos_match.group(1))
                curr_target, curr_actual, curr_delta = None, None, None
                continue

            coord_match = re.search(
                r'(target|actual|delta)\s*:\s*\{\s*([^,}]+),\s*([^,}]+),\s*([^}]+)\}\s*\|\s*([^ ]+)\s*deg',
                line_str,
                re.IGNORECASE,
            )
            if coord_match and current_pos is not None:
                kind = coord_match.group(1).lower()
                x = float(coord_match.group(2))
                y = float(coord_match.group(3))
                z = float(coord_match.group(4))
                rot = coerce_rotation(float(coord_match.group(5)))
                vec = [x, y, z, rot]
                if kind == "target":
                    curr_target = vec
                elif kind == "actual":
                    curr_actual = vec
                elif kind == "delta":
                    curr_delta = vec

        if current_pos is not None and curr_target and curr_actual and curr_delta:
            positions[current_pos] = SurveyPositionData(
                target=curr_target, actual=curr_actual, delta=curr_delta
            )

    return SurveyData(
        stage=stage,
        file_path=file_path,
        timestamp=timestamp,
        positions=positions,
    )


def discover_and_parse_directory(dir_path: Path | str) -> TestRunData:
    """Scan a module test run directory, discover all relevant files, and parse matrices/curves."""
    path = Path(dir_path)
    if not path.is_dir():
        raise FileNotFoundError(f"Directory not found: {path}")
        
    metadata = extract_metadata_from_path(path)
    run_data = TestRunData(directory=path, metadata=metadata)
    
    # Scan files in directory
    for item in sorted(path.iterdir()):
        if not item.is_file():
            continue
        fname = item.name.lower()
        
        # Check for baseline YAML: e.g. module_40229_etroc_0_baseline_auto.yaml
        bl_match = re.search(r'etroc[_-]?([0-3])[_-]baseline', fname)
        if bl_match and (fname.endswith('.yaml') or fname.endswith('.yml')):
            pos = int(bl_match.group(1))
            run_data.baseline_files[pos] = item
            # Try to refine module serial from file name if not already extracted
            if not run_data.metadata.module:
                mod_f_match = re.search(r'module[_-]([0-9A-Za-z]+)[_-]etroc', item.name, re.IGNORECASE)
                if mod_f_match:
                    run_data.metadata.module = mod_f_match.group(1)
            continue
            
        # Check for noise width YAML: e.g. module_40229_etroc_0_noise_width_auto.yaml
        nw_match = re.search(r'etroc[_-]?([0-3])[_-]noise[_-]?width', fname)
        if nw_match and (fname.endswith('.yaml') or fname.endswith('.yml')):
            pos = int(nw_match.group(1))
            run_data.noisewidth_files[pos] = item
            if not run_data.metadata.module:
                mod_f_match = re.search(r'module[_-]([0-9A-Za-z]+)[_-]etroc', item.name, re.IGNORECASE)
                if mod_f_match:
                    run_data.metadata.module = mod_f_match.group(1)
            continue
            
        # Check for IV CSV: e.g. IV_Curve_40229_2026-09-15-11-59-06.csv
        if ('iv_curve' in fname or 'iv-curve' in fname or fname.startswith('iv_')) and fname.endswith('.csv'):
            run_data.iv_file = item
            if not run_data.metadata.module:
                mod_f_match = re.search(r'iv[_-]curve[_-]([0-9A-Za-z]+)[_-]', fname)
                if mod_f_match:
                    run_data.metadata.module = mod_f_match.group(1)
            # If measurement date wasn't found from folder name, try IV curve filename
            if not run_data.metadata.measurement_date:
                date_match = re.search(r'(\d{4})-(\d{2})-(\d{2})[-_](\d{2})[-_](\d{2})[-_](\d{2})', item.name)
                if date_match:
                    y, m, d, hh, mm, ss = map(int, date_match.groups())
                    run_data.metadata.measurement_date = datetime.datetime(y, m, d, hh, mm, ss, tzinfo=pytz.utc)
            continue

        # Check for alignment survey TXT: e.g. H4_ETROC_Survey_Precure_2026-09-11--16-39-13.txt
        survey_match = re.search(r'H4[_-]?ETROC[_-]?Survey[_-]?(Precure|Postcure)[-_]?(.*)\.txt$', item.name, re.IGNORECASE)
        if survey_match:
            stage_key = survey_match.group(1).lower()
            run_data.survey_files[stage_key] = item
            continue

    # Parse baseline matrices
    for pos, bfile in run_data.baseline_files.items():
        try:
            run_data.baseline_matrices[pos] = parse_yaml_matrix(bfile)
        except Exception as e:
            run_data.warnings.append(f"Failed to parse baseline file pos {pos} ({bfile.name}): {e}")

    # Parse noisewidth matrices
    for pos, nwfile in run_data.noisewidth_files.items():
        try:
            run_data.noisewidth_matrices[pos] = parse_yaml_matrix(nwfile)
        except Exception as e:
            run_data.warnings.append(f"Failed to parse noisewidth file pos {pos} ({nwfile.name}): {e}")

    # Parse IV CSV
    if run_data.iv_file:
        try:
            run_data.iv_data = parse_iv_csv(run_data.iv_file)
        except Exception as e:
            run_data.warnings.append(f"Failed to parse IV CSV ({run_data.iv_file.name}): {e}")
    else:
        run_data.warnings.append("No IV curve CSV file found in directory")

    # Parse Survey files
    for stage_key, sfile in run_data.survey_files.items():
        try:
            run_data.survey_data[stage_key] = parse_survey_file(sfile)
        except Exception as e:
            run_data.warnings.append(f"Failed to parse survey file ({sfile.name}): {e}")

    # Check for missing chips (0-3)
    missing_bl = set(range(4)) - set(run_data.baseline_matrices.keys())
    if missing_bl:
        run_data.warnings.append(f"Missing baseline data for ETROC position(s): {sorted(missing_bl)}")
        
    missing_nw = set(range(4)) - set(run_data.noisewidth_matrices.keys())
    if missing_nw:
        run_data.warnings.append(f"Missing noisewidth data for ETROC position(s): {sorted(missing_nw)}")

    return run_data
