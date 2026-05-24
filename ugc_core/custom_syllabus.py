"""Build a Subject from user-entered name + syllabus text (paste or file)."""

from __future__ import annotations

import re
from pathlib import Path

from pypdf import PdfReader

from .models import Subject
from .syllabus_parser import (
    _normalize,
    _parse_description,
    _parse_objectives,
    _parse_units,
    extract_pdf_text,
)


def detect_credits(syllabus_text: str) -> int | None:
    """Find credit value mentioned in syllabus text."""
    patterns = [
        r"(?:Credits?|CREDIT)\s*[:\-]?\s*(\d+)",
        r"(?:^|\n)\s*Credit\s+(\d+)\s",
        r"(\d+)\s+Credits?\b",
        r"Course\s+Credits?\s*[:\-]?\s*(\d+)",
        r"(?:CC|AEC|SEC|FC)\s+(\d+)\s*(?:\n|$)",
        r"L\s+T\s+P[^\n]*\b(\d)\s*(?:\n|$)",
    ]
    for pattern in patterns:
        m = re.search(pattern, syllabus_text, re.IGNORECASE | re.MULTILINE)
        if m:
            value = int(m.group(1))
            if 1 <= value <= 10:
                return value
    return None


def load_syllabus_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return extract_pdf_text(path)
    if suffix in (".txt", ".md"):
        return _normalize(path.read_text(encoding="utf-8", errors="replace"))
    if suffix == ".docx":
        from docx import Document

        doc = Document(str(path))
        return _normalize("\n".join(p.text for p in doc.paragraphs if p.text.strip()))
    raise ValueError(f"Unsupported file type: {suffix}. Use .txt, .pdf, or .docx")


def subject_from_syllabus(
    subject_name: str,
    syllabus_text: str,
    *,
    credits: int | None = None,
) -> Subject:
    """
    Parse user syllabus into a Subject.

    - Units: Unit I, Unit II, … (Rule 3)
    - Credits: explicit arg > detected in text > number of units > 3
    """
    text = _normalize(syllabus_text)
    if not text.strip():
        raise ValueError("Syllabus text is empty.")

    name = subject_name.strip()
    if not name:
        raise ValueError("Subject name is required.")

    units = _parse_units(text)
    detected = detect_credits(text)
    final_credits = credits or detected or (len(units) if units else 3)
    final_credits = max(1, min(10, final_credits))

    intro = ""
    block = text
    if not re.search(r"Course Description\s*:", text, re.I):
        if units:
            first_unit = re.search(
                r"(?:^|\n)\s*Unit\s*(?:[-–—]\s*)?[IVXLCDM\d]+",
                text,
                re.I | re.M,
            )
            intro = text[: first_unit.start()].strip() if first_unit else text[:800]
        else:
            intro = text[:1200]
        block = f"Course Description:\n{intro}\n\n{text}"

    description = _parse_description(block) or intro or text[:1200]

    return Subject(
        name=name,
        credits=final_credits,
        description=description,
        objectives=_parse_objectives(block),
        syllabus_units=units,
    )
