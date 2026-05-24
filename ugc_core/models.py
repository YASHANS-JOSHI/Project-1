from dataclasses import dataclass, field


@dataclass
class SyllabusUnit:
    number: int
    label: str  # e.g. "I", "II"
    content: str
    topics: list[str] = field(default_factory=list)


@dataclass
class Subject:
    name: str
    credits: int
    semester: str | None = None
    description: str = ""
    objectives: list[str] = field(default_factory=list)
    syllabus_units: list[SyllabusUnit] = field(default_factory=list)
    course_outcomes: list[str] = field(default_factory=list)


@dataclass
class PlannedUnit:
    number: int
    label: str
    title: str
    content: str
    topics: list[str]
    source: str  # "pdf" | "credit"


@dataclass
class ContentSlide:
    title: str
    bullets: list[str] = field(default_factory=list)
    visual_suggestion: str = ""
    speaker_notes: str = ""


@dataclass
class UnitContentPackage:
    """Generated teaching pack for one unit."""

    unit_title: str
    introduction: str
    learning_objectives: list[str]
    topic_slides: list[ContentSlide]
    case_study: str
    summary: str
    keywords: list[str]
    saqs: list[str]
    saq_answers: list[str]
    references: list[str]
    check_your_progress: list[str]
    transcript: str
    target_slide_count: int = 12
    minutes_per_unit: int = 80
    words_target_slm: int = 0
    generated_by: str = "template"  # "template" | "ai:openai" | "ai:groq"
    ai_error: str | None = None
