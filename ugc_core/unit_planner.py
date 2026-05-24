"""Unit planning: Rule 1 (credits = units) + Rule 3 (PDF syllabus overrides)."""

from .models import PlannedUnit, Subject, SyllabusUnit


def _topics_from_content(content: str, max_topics: int = 6) -> list[str]:
    text = content.replace("\n", " ").strip()
    if not text:
        return []
    parts = [p.strip() for p in text.split(".") if len(p.strip()) > 12]
    if len(parts) < 2:
        parts = [p.strip() for p in text.split(",") if len(p.strip()) > 8]
    return parts[:max_topics] if parts else [text[:200]]


def _unit_title(subject_name: str, number: int, label: str) -> str:
    return f"{subject_name} — Unit {label}"


def plan_units(subject: Subject) -> list[PlannedUnit]:
    """
    Rule 3: If the PDF provides syllabus units, use them as-is.
    Rule 1: Otherwise, create `credits` empty units (1 credit = 1 unit).
    """
    if subject.syllabus_units:
        planned: list[PlannedUnit] = []
        for u in subject.syllabus_units:
            topics = u.topics or _topics_from_content(u.content)
            planned.append(
                PlannedUnit(
                    number=u.number,
                    label=u.label,
                    title=_unit_title(subject.name, u.number, u.label),
                    content=u.content,
                    topics=topics,
                    source="pdf",
                )
            )
        return planned

    count = max(1, subject.credits)
    planned = []
    for i in range(count):
        n = i + 1
        label = str(n)
        planned.append(
            PlannedUnit(
                number=n,
                label=label,
                title=_unit_title(subject.name, n, label),
                content="",
                topics=[],
                source="credit",
            )
        )
    return planned
