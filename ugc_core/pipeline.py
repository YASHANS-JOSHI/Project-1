"""Full export: SLM + expanded PPT + transcript + storyboard per unit."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .content_engine import generate_unit_content
from .models import PlannedUnit, Subject, UnitContentPackage
from .ppt_generator import generate_unit_ppt
from .slm_generator import generate_slm_docx
from .storyboard_generator import generate_storyboard_docx
from .transcript_generator import generate_transcript_docx
from .ugc_rules import UnitMetrics, compute_unit_metrics
from .unit_planner import plan_units


@dataclass
class UnitExportBundle:
    unit: PlannedUnit
    pack: UnitContentPackage
    metrics: UnitMetrics
    ppt: Path | None = None
    slm: Path | None = None
    transcript: Path | None = None
    storyboard: Path | None = None


@dataclass
class SubjectExportResult:
    subject: Subject
    output_dir: Path
    units: list[UnitExportBundle] = field(default_factory=list)


def export_subject(
    subject: Subject,
    output_dir: Path,
    template_path: Path,
    *,
    program_name: str,
    course_code: str,
    delivered_by: str = "",
    use_ai: bool | None = None,
    include_storyboard: bool = True,
    student_friendly: bool = True,
    api_key: str | None = None,
    model: str | None = None,
    provider: str | None = None,
) -> SubjectExportResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    units = plan_units(subject)
    unit_count = len(units)
    metrics = compute_unit_metrics(subject.credits, unit_count)
    safe = re.sub(r"[^\w\-]+", "_", subject.name)[:50].strip("_")
    result = SubjectExportResult(subject=subject, output_dir=output_dir)

    for unit in units:
        pack = generate_unit_content(
            subject,
            unit,
            unit_count,
            use_ai=use_ai,
            api_key=api_key,
            model=model,
            provider=provider,
            student_friendly=student_friendly,
        )
        unit_dir = output_dir / f"Unit_{unit.label}"
        unit_dir.mkdir(parents=True, exist_ok=True)

        ppt_path = unit_dir / f"{safe}_Unit_{unit.label}.pptx"
        slm_path = unit_dir / f"{safe}_Unit_{unit.label}_SLM.docx"
        transcript_path = unit_dir / f"{safe}_Unit_{unit.label}_Transcript.docx"
        storyboard_path = unit_dir / f"{safe}_Unit_{unit.label}_Storyboard.docx"

        generate_unit_ppt(
            template_path,
            ppt_path,
            program_name=program_name,
            course_code=course_code,
            subject=subject,
            unit=unit,
            pack=pack,
            delivered_by=delivered_by,
        )
        generate_slm_docx(
            slm_path,
            program_name=program_name,
            subject=subject,
            unit_label=unit.label,
            pack=pack,
        )
        generate_transcript_docx(
            transcript_path,
            program_name=program_name,
            subject=subject,
            unit_label=unit.label,
            pack=pack,
            delivered_by=delivered_by,
        )
        sb = None
        if include_storyboard:
            generate_storyboard_docx(storyboard_path, pack=pack)
            sb = storyboard_path

        result.units.append(
            UnitExportBundle(
                unit=unit,
                pack=pack,
                metrics=metrics,
                ppt=ppt_path,
                slm=slm_path,
                transcript=transcript_path,
                storyboard=sb,
            )
        )
    return result
