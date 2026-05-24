"""Parse UGC-style MBA syllabus PDF: subjects, credits, and unit content."""

from __future__ import annotations

import re
from pathlib import Path

from pypdf import PdfReader

from .models import Subject, SyllabusUnit

ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8}


def _normalize(text: str) -> str:
    text = text.replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def _roman_to_int(label: str) -> int:
    label = label.strip().upper()
    if label.isdigit():
        return int(label)
    return ROMAN.get(label, 0)


def _int_to_roman(n: int) -> str:
    for k, v in ROMAN.items():
        if v == n:
            return k
    return str(n)


def extract_pdf_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    parts = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return _normalize("\n".join(parts))


def _parse_credit_table(text: str) -> dict[str, int]:
    """Best-effort credits from programme structure tables."""
    credits: dict[str, int] = {}
    # e.g. Marketing Management 3 0 0 20 10 30 70 100 CC 4
    pattern = re.compile(
        r"(?P<name>[A-Za-z][A-Za-z\s&,\-\(\)]+?)\s+"
        r"\d\s+0\s+(?:\d\s+)?0\s+"
        r"20\s+10\s+30\s+70\s+100\s+"
        r"(?:CC|AE|SEC|AEC|FC)\s+"
        r"(?P<credit>\d+)",
        re.MULTILINE,
    )
    for m in pattern.finditer(text):
        name = re.sub(r"\s+", " ", m.group("name")).strip()
        if len(name) > 4:
            credits[name.lower()] = int(m.group("credit"))

    # Multiline subject + credit on next lines (Management Concepts & Organizational Behavior \n\n 3)
    multiline = re.compile(
        r"(?P<name>[A-Za-z][A-Za-z\s&,\-\(\)]+?)\s*\n+\s*(?P<credit>[1-6])\s*\n+"
        r"(?:0\s+0|Course Description)",
        re.MULTILINE,
    )
    for m in multiline.finditer(text):
        name = re.sub(r"\s+", " ", m.group("name")).strip()
        if len(name) > 8:
            credits[name.lower()] = int(m.group("credit"))
    return credits


def _match_credit(name: str, credit_map: dict[str, int]) -> int:
    key = name.lower().strip()
    if key in credit_map:
        return credit_map[key]
    for k, v in credit_map.items():
        if k in key or key in k:
            return v
    # fuzzy: first word overlap
    words = set(key.split())
    best = 0
    best_score = 0
    for k, v in credit_map.items():
        kw = set(k.split())
        score = len(words & kw)
        if score > best_score:
            best_score = score
            best = v
    return best if best_score >= 2 else 4  # default MBA core credit


def _parse_objectives(block: str) -> list[str]:
    objs = []
    in_obj = False
    for line in block.split("\n"):
        s = line.strip()
        if re.match(r"Course Objectives\s*:", s, re.I):
            in_obj = True
            continue
        if in_obj:
            if re.match(r"Course Content\s*:", s, re.I):
                break
            if s.startswith("•") or s.startswith("") or s.startswith("-"):
                objs.append(s.lstrip("•- ").strip())
            elif s and not s.startswith("Course"):
                objs.append(s)
    return [o for o in objs if len(o) > 10][:8]


def _parse_description(block: str) -> str:
    m = re.search(
        r"Course Description:\s*(.*?)(?=Course Objectives:|Course Content:|$)",
        block,
        re.DOTALL | re.I,
    )
    if not m:
        return ""
    return re.sub(r"\s+", " ", m.group(1)).strip()


def _parse_units(block: str) -> list[SyllabusUnit]:
    units: list[SyllabusUnit] = []
    # Line-start only; PDFs use mixed dashes and sometimes omit colons
    unit_pattern = re.compile(
        r"(?:^|\n)\s*Unit\s*(?:[-–—]\s*)?([IVXLCDM\d]+)\s*:?\s*",
        re.IGNORECASE | re.MULTILINE,
    )
    matches = list(unit_pattern.finditer(block))
    if not matches:
        return units

    # Drop false positives: keep first match per roman label in order
    seen_labels: list[str] = []
    filtered = []
    for m in matches:
        label = m.group(1).upper()
        if label in seen_labels:
            continue
        seen_labels.append(label)
        filtered.append(m)
    matches = filtered

    for i, m in enumerate(matches):
        label = m.group(1).upper()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(block)
        chunk = block[start:end]
        # stop at outcomes / readings
        chunk = re.split(
            r"Course Outcomes|Suggested Readings|Assessment Method",
            chunk,
            maxsplit=1,
            flags=re.I,
        )[0]
        content = re.sub(r"\s+", " ", chunk).strip()
        num = _roman_to_int(label) or (i + 1)
        topics = [t.strip() for t in re.split(r"(?<=[a-z])\.\s+", content) if len(t.strip()) > 15][:6]
        units.append(
            SyllabusUnit(number=num, label=label if label in ROMAN else _int_to_roman(num), content=content, topics=topics)
        )
    return units


def _parse_subject_blocks(text: str) -> list[tuple[str, str, str | None]]:
    """Return (name, body, semester) for each detailed syllabus section."""
    results: list[tuple[str, str, str | None]] = []
    sections = re.split(r"(SEMESTER\s*[–-]\s*[IVX\d]+)", text, flags=re.I)
    semester = None
    i = 0
    while i < len(sections):
        part = sections[i].strip()
        if re.match(r"SEMESTER\s*[–-]", part, re.I):
            semester = part
            i += 1
            if i < len(sections):
                body = sections[i]
                # subject blocks: ALL CAPS title before Course Description
                for m in re.finditer(
                    r"\n([A-Z][A-Z0-9\s&,\-\(\)']{8,}?)\s*\n+\s*Course Description:",
                    body,
                ):
                    name = re.sub(r"\s+", " ", m.group(1)).strip()
                    if "TABLE" in name or "ELECTIVE" in name and "COURSES" in name:
                        continue
                    start = m.start()
                    next_m = re.search(
                        r"\n[A-Z][A-Z0-9\s&,\-\(\)']{8,}?\s*\n+\s*Course Description:",
                        body[m.end() :],
                    )
                    end = m.end() + next_m.start() if next_m else len(body)
                    block = body[start:end]
                    results.append((name, block, semester))
            i += 1
        else:
            i += 1
    return results


def parse_mba_syllabus(pdf_path: Path) -> list[Subject]:
    text = extract_pdf_text(pdf_path)
    credit_map = _parse_credit_table(text)
    subjects: list[Subject] = []
    seen: set[str] = set()

    for name, block, semester in _parse_subject_blocks(text):
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        units = _parse_units(block)
        if not units:
            continue
        credits = _match_credit(name, credit_map)
        subjects.append(
            Subject(
                name=name.title() if name.isupper() else name,
                credits=credits,
                semester=semester,
                description=_parse_description(block),
                objectives=_parse_objectives(block),
                syllabus_units=units,
            )
        )
    return subjects


def load_subjects(pdf_path: Path) -> list[Subject]:
    if not pdf_path.exists():
        raise FileNotFoundError(f"Syllabus PDF not found: {pdf_path}")
    return parse_mba_syllabus(pdf_path)
