"""Model generation and validation using etlup Pydantic schemas."""

from dataclasses import dataclass, field
import datetime
from typing import Any, List, Optional
import pytz

from etlup.tamalero.Baseline import BaselineV0
from etlup.tamalero.Noisewidth import NoisewidthV0
from etlup.module.ModuleIV import ModuleIVV0
from etlup.gantry.SubassemblyAlignment import HybridAlignmentPosition, SubassemblyAlignmentV1
from etlgup.parser import SurveyData, TestRunData


@dataclass
class UploadBatch:
    baseline: Optional[BaselineV0] = None
    noisewidth: Optional[NoisewidthV0] = None
    module_iv: Optional[ModuleIVV0] = None
    module_ivs: List[ModuleIVV0] = field(default_factory=list)
    precure_alignment: Optional[SubassemblyAlignmentV1] = None
    postcure_alignment: Optional[SubassemblyAlignmentV1] = None
    subassembly_alignments: List[SubassemblyAlignmentV1] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.module_iv is not None and not self.module_ivs:
            self.module_ivs = [self.module_iv]
        elif self.module_ivs and self.module_iv is None:
            self.module_iv = self.module_ivs[0]

        if self.precure_alignment is not None and self.precure_alignment not in self.subassembly_alignments:
            self.subassembly_alignments.append(self.precure_alignment)
        if self.postcure_alignment is not None and self.postcure_alignment not in self.subassembly_alignments:
            self.subassembly_alignments.append(self.postcure_alignment)

    @property
    def total_count(self) -> int:
        count = 0
        if self.baseline is not None:
            count += 1
        if self.noisewidth is not None:
            count += 1
        if self.module_iv is not None:
            count += 1
        elif self.module_ivs:
            count += len(self.module_ivs)
        count += len(self.subassembly_alignments)
        return count

    def all_models(self) -> List[Any]:
        models: List[Any] = []
        if self.baseline is not None:
            models.append(self.baseline)
        if self.noisewidth is not None:
            models.append(self.noisewidth)
        if self.module_iv is not None:
            models.append(self.module_iv)
        elif self.module_ivs:
            models.extend(self.module_ivs)
        models.extend(self.subassembly_alignments)
        return models

    def filter_tests(
        self,
        include_baseline: bool = True,
        include_noisewidth: bool = True,
        include_module_iv: bool = True,
        include_precure_alignment: bool = True,
        include_postcure_alignment: bool = True,
    ) -> "UploadBatch":
        """Return a new UploadBatch containing only the selected test records."""
        subassembly_alignments: List[SubassemblyAlignmentV1] = []
        precure = self.precure_alignment if include_precure_alignment else None
        postcure = self.postcure_alignment if include_postcure_alignment else None
        if precure is not None:
            subassembly_alignments.append(precure)
        if postcure is not None:
            subassembly_alignments.append(postcure)

        for sa in self.subassembly_alignments:
            if sa is not self.precure_alignment and sa is not self.postcure_alignment:
                subassembly_alignments.append(sa)

        mod_iv = self.module_iv if include_module_iv else None
        mod_ivs = list(self.module_ivs) if include_module_iv else []

        return UploadBatch(
            baseline=self.baseline if include_baseline else None,
            noisewidth=self.noisewidth if include_noisewidth else None,
            module_iv=mod_iv,
            module_ivs=mod_ivs,
            precure_alignment=precure,
            postcure_alignment=postcure,
            subassembly_alignments=subassembly_alignments,
        )

    def filter_by_keys(self, selected_keys: Any) -> "UploadBatch":
        """Filter batch models based on an iterable of selected test keys."""
        norm_keys = set()
        for k in selected_keys:
            kl = str(k).lower().replace(" ", "_")
            if kl in ("baseline", "base_line"):
                norm_keys.add("baseline")
            elif kl in ("noisewidth", "noise_width", "noise"):
                norm_keys.add("noisewidth")
            elif kl in ("module_iv", "iv", "iv_curve", "moduleiv"):
                norm_keys.add("module_iv")
            elif kl in ("precure_alignment", "precure", "pre_cure"):
                norm_keys.add("precure_alignment")
            elif kl in ("postcure_alignment", "postcure", "post_cure"):
                norm_keys.add("postcure_alignment")
            else:
                norm_keys.add(kl)

        return self.filter_tests(
            include_baseline="baseline" in norm_keys,
            include_noisewidth="noisewidth" in norm_keys,
            include_module_iv="module_iv" in norm_keys,
            include_precure_alignment="precure_alignment" in norm_keys,
            include_postcure_alignment="postcure_alignment" in norm_keys,
        )


def create_baseline_model(
    run_data: TestRunData,
    location: str,
    user_created: str,
    module: Optional[str] = None,
    measurement_date: Optional[datetime.datetime] = None,
    bias_volts: Optional[float] = None,
) -> Optional[BaselineV0]:
    """Create and validate BaselineV0 model from parsed run data."""
    if not run_data.baseline_matrices:
        return None

    mod = str(module or run_data.metadata.module or "")
    mdate = measurement_date or run_data.metadata.measurement_date or datetime.datetime.now(pytz.utc)
    if mdate.tzinfo is None:
        mdate = pytz.utc.localize(mdate)
    bvolts = bias_volts if bias_volts is not None else run_data.metadata.bias_volts

    kwargs: dict[str, Any] = {
        "module": mod,
        "location": location,
        "user_created": user_created,
        "measurement_date": mdate,
        "bias_volts": bvolts,
    }
    for pos in (0, 1, 2, 3):
        if pos in run_data.baseline_matrices:
            kwargs[f"pos_{pos}"] = run_data.baseline_matrices[pos]

    return BaselineV0(**kwargs)


def create_noisewidth_model(
    run_data: TestRunData,
    location: str,
    user_created: str,
    module: Optional[str] = None,
    measurement_date: Optional[datetime.datetime] = None,
    bias_volts: Optional[float] = None,
) -> Optional[NoisewidthV0]:
    """Create and validate NoisewidthV0 model from parsed run data."""
    if not run_data.noisewidth_matrices:
        return None

    mod = str(module or run_data.metadata.module or "")
    mdate = measurement_date or run_data.metadata.measurement_date or datetime.datetime.now(pytz.utc)
    if mdate.tzinfo is None:
        mdate = pytz.utc.localize(mdate)
    bvolts = bias_volts if bias_volts is not None else run_data.metadata.bias_volts

    kwargs: dict[str, Any] = {
        "module": mod,
        "location": location,
        "user_created": user_created,
        "measurement_date": mdate,
        "bias_volts": bvolts,
    }
    for pos in (0, 1, 2, 3):
        if pos in run_data.noisewidth_matrices:
            kwargs[f"pos_{pos}"] = run_data.noisewidth_matrices[pos]

    return NoisewidthV0(**kwargs)


def create_module_iv_model(
    run_data: TestRunData,
    location: str,
    user_created: str,
    module: Optional[str] = None,
    measurement_date: Optional[datetime.datetime] = None,
    component_pos: int = 0,
) -> Optional[ModuleIVV0]:
    """Create and validate a single ModuleIVV0 model from parsed IV data."""
    if not run_data.iv_data:
        return None

    mod = str(module or run_data.metadata.module or "")
    mdate = measurement_date or run_data.metadata.measurement_date or datetime.datetime.now(pytz.utc)
    if mdate.tzinfo is None:
        mdate = pytz.utc.localize(mdate)

    return ModuleIVV0(
        module=mod,
        component_pos=component_pos,
        current=run_data.iv_data["current"],
        voltage=run_data.iv_data["voltage"],
        k_factor=run_data.iv_data.get("k_factor"),
        location=location,
        user_created=user_created,
        measurement_date=mdate,
    )


def create_module_iv_models(
    run_data: TestRunData,
    location: str,
    user_created: str,
    module: Optional[str] = None,
    measurement_date: Optional[datetime.datetime] = None,
    positions: Optional[tuple[int, ...]] = None,
) -> List[ModuleIVV0]:
    """Create and validate ModuleIVV0 model(s). Defaults to a single measurement at component_pos=0."""
    if not run_data.iv_data:
        return []

    if positions is not None:
        mod = str(module or run_data.metadata.module or "")
        mdate = measurement_date or run_data.metadata.measurement_date or datetime.datetime.now(pytz.utc)
        if mdate.tzinfo is None:
            mdate = pytz.utc.localize(mdate)

        models: List[ModuleIVV0] = []
        for pos in positions:
            m = ModuleIVV0(
                module=mod,
                component_pos=pos,
                current=run_data.iv_data["current"],
                voltage=run_data.iv_data["voltage"],
                k_factor=run_data.iv_data.get("k_factor"),
                location=location,
                user_created=user_created,
                measurement_date=mdate,
            )
            models.append(m)
        return models

    single_model = create_module_iv_model(
        run_data=run_data,
        location=location,
        user_created=user_created,
        module=module,
        measurement_date=measurement_date,
        component_pos=0,
    )
    return [single_model] if single_model is not None else []


def create_subassembly_alignment_model(
    survey: SurveyData,
    location: str,
    user_created: str,
    module: Optional[str] = None,
    measurement_date: Optional[datetime.datetime] = None,
) -> Optional[SubassemblyAlignmentV1]:
    """Create and validate a SubassemblyAlignmentV1 model for an alignment survey."""
    if not survey or not survey.positions:
        return None

    mod = str(module or "")
    mdate = survey.timestamp or measurement_date or datetime.datetime.now(pytz.utc)
    if mdate.tzinfo is None:
        mdate = pytz.utc.localize(mdate)

    pos_kwargs: dict[str, Any] = {}
    for p in range(4):
        if p in survey.positions:
            pdata = survey.positions[p]
            pos_kwargs[f"position_{p}"] = HybridAlignmentPosition(
                target=pdata.target,
                actual=pdata.actual,
                delta=pdata.delta,
            )

    if not pos_kwargs:
        return None

    return SubassemblyAlignmentV1(
        module=mod,
        location=location,
        user_created=user_created,
        measurement_date=mdate,
        **pos_kwargs,
    )


def build_upload_batch(
    run_data: TestRunData,
    location: str,
    user_created: str,
    module: Optional[str] = None,
    measurement_date: Optional[datetime.datetime] = None,
    bias_volts: Optional[float] = None,
) -> UploadBatch:
    """Build all validated upload models into an UploadBatch."""
    mod = str(module or run_data.metadata.module or "")
    baseline = create_baseline_model(
        run_data=run_data,
        location=location,
        user_created=user_created,
        module=mod,
        measurement_date=measurement_date,
        bias_volts=bias_volts,
    )
    noisewidth = create_noisewidth_model(
        run_data=run_data,
        location=location,
        user_created=user_created,
        module=mod,
        measurement_date=measurement_date,
        bias_volts=bias_volts,
    )
    module_iv = create_module_iv_model(
        run_data=run_data,
        location=location,
        user_created=user_created,
        module=mod,
        measurement_date=measurement_date,
    )

    precure_alignment: Optional[SubassemblyAlignmentV1] = None
    if "precure" in run_data.survey_data:
        precure_alignment = create_subassembly_alignment_model(
            survey=run_data.survey_data["precure"],
            location=location,
            user_created=user_created,
            module=mod,
            measurement_date=measurement_date,
        )

    postcure_alignment: Optional[SubassemblyAlignmentV1] = None
    if "postcure" in run_data.survey_data:
        postcure_alignment = create_subassembly_alignment_model(
            survey=run_data.survey_data["postcure"],
            location=location,
            user_created=user_created,
            module=mod,
            measurement_date=measurement_date,
        )

    subassembly_alignments: List[SubassemblyAlignmentV1] = []
    if precure_alignment is not None:
        subassembly_alignments.append(precure_alignment)
    if postcure_alignment is not None:
        subassembly_alignments.append(postcure_alignment)
    for stage_key, sdata in run_data.survey_data.items():
        if stage_key not in ("precure", "postcure"):
            extra_align = create_subassembly_alignment_model(
                survey=sdata,
                location=location,
                user_created=user_created,
                module=mod,
                measurement_date=measurement_date,
            )
            if extra_align is not None:
                subassembly_alignments.append(extra_align)

    return UploadBatch(
        baseline=baseline,
        noisewidth=noisewidth,
        module_iv=module_iv,
        module_ivs=[module_iv] if module_iv is not None else [],
        precure_alignment=precure_alignment,
        postcure_alignment=postcure_alignment,
        subassembly_alignments=subassembly_alignments,
    )
