"""Generate SLM/PPT/transcript content via LLM API or syllabus-based fallback."""

from __future__ import annotations

import re
from typing import Any

from .ai_client import AIClientError, AIConfig, chat_json, resolve_ai_config
from .models import ContentSlide, PlannedUnit, Subject, UnitContentPackage
from .ugc_rules import UnitMetrics, compute_unit_metrics

DEFAULT_REFERENCES = [
    "UGC e-PG Pathshala resources",
    "Prescribed university syllabus readings",
]

STUDENT_SYSTEM = """You are an expert university teacher creating e-learning content for Indian UG/PG students.

Write so a first-time learner can understand:
- Use clear, simple English (B1–B2 level). Define jargon in plain words.
- Short sentences. Active voice.
- Each slide bullet = ONE idea, max 12 words, no nested clauses.
- Use "Example:", "Remember:", or "Think:" prefixes where helpful.
- Give relatable Indian business / daily-life examples (startups, banks, retail, Ola, UPI, etc.).
- Follow the 6×6 rule: max 6 bullets per slide, ~6 words per bullet when possible.
- Bloom's taxonomy for objectives (4 clear, measurable outcomes).
- Output ONLY valid JSON matching the user's schema. No markdown fences."""

ACADEMIC_SYSTEM = """You are an academic SME creating UGC-aligned e-content for Indian universities.
Use a professional but accessible tone. Output ONLY valid JSON. No markdown."""


def _split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if len(p.strip()) > 20]


def _chunk_for_slides(text: str, n_slides: int) -> list[list[str]]:
    sentences = _split_sentences(text)
    if not sentences:
        return [["Key idea: core concepts for this unit"]] * max(3, n_slides - 6)
    per = max(1, len(sentences) // max(1, n_slides - 6))
    chunks: list[list[str]] = []
    i = 0
    while i < len(sentences) and len(chunks) < n_slides - 6:
        group = sentences[i : i + per]
        bullets = []
        for s in group[:5]:
            words = s.split()
            short = " ".join(words[:10])
            bullets.append(short + ("…" if len(words) > 10 else ""))
        chunks.append(bullets or [group[0][:100]])
        i += per
    while len(chunks) < max(3, n_slides - 6):
        chunks.append(
            [
                "Remember: link theory to real decisions",
                "Example: discuss one company you know",
            ]
        )
    return chunks


def _template_package(
    subject: Subject,
    unit: PlannedUnit,
    metrics: UnitMetrics,
    *,
    student_friendly: bool = True,
) -> UnitContentPackage:
    content_slides_needed = max(3, min(15, metrics.target_slides - 6))
    chunks = _chunk_for_slides(unit.content or unit.title, content_slides_needed)

    topic_slides: list[ContentSlide] = []
    topics = unit.topics or [unit.title]
    for i, bullets in enumerate(chunks):
        title = topics[i % len(topics)][:100] if topics else f"Topic {i + 1}"
        if student_friendly:
            bullets = [
                b if b.startswith(("Example:", "Remember:", "Think:")) else b
                for b in bullets
            ]
        topic_slides.append(
            ContentSlide(
                title=title,
                bullets=bullets[:5],
                visual_suggestion=f"Simple diagram: {title[:40]}",
                speaker_notes="Explain in everyday language. Ask: 'Can you think of an example?'",
            )
        )

    intro = (
        f"In this unit you will learn the basics of {subject.name} (Unit {unit.label}). "
        f"We keep concepts simple with examples. "
        f"{unit.content[:350] if unit.content else ''}"
    ).strip()

    objectives = subject.objectives[:4] if subject.objectives else [
        f"Explain key ideas in {unit.title} in your own words",
        "Use examples from business or daily life",
        "Solve a short case using unit concepts",
        "Compare two approaches and say when to use each",
    ]

    summary_bits = unit.topics[-4:] if unit.topics else _split_sentences(unit.content)[:4]
    summary = (
        "What you learned: " + "; ".join(summary_bits[:4])
        if summary_bits
        else "Review the slides and try the practice questions."
    )

    saqs = [
        f"In simple words, what is the main idea of Unit {unit.label}?",
        "Give one real-world example from this unit.",
        "What would you do differently after studying this unit?",
    ]
    answers = [
        "State the core definition and one supporting point from the unit.",
        "Name a company, product, or situation and link it to the concept.",
        "Mention one decision or habit you would change, with reason.",
    ]

    transcript_parts = [
        f"Hello! Welcome to {unit.title}. "
        f"We have about {metrics.minutes_per_unit} minutes together. "
        f"I will explain everything step by step—feel free to pause and note examples.\n\n",
        intro + "\n\n",
    ]
    for slide in topic_slides:
        transcript_parts.append(
            f"Now look at the slide: {slide.title}. "
            + " ".join(slide.bullets)
            + "\nLet me give you a simple example from Indian business context.\n\n"
        )
    transcript_parts.append(f"Before we end: {summary}\n\nGreat work today. Happy learning!")
    transcript = "".join(transcript_parts)

    return UnitContentPackage(
        unit_title=unit.title,
        introduction=intro,
        learning_objectives=objectives,
        topic_slides=topic_slides,
        case_study=(
            f"Think like a manager: pick a company you know. "
            f"How would Unit {unit.label} ideas from {subject.name} help them? "
            f"Write 150 words with one clear recommendation."
        ),
        summary=summary,
        keywords=(unit.topics[:8] or [subject.name, f"Unit {unit.label}"]),
        saqs=saqs,
        saq_answers=answers,
        references=DEFAULT_REFERENCES,
        check_your_progress=[
            "Can you teach this topic to a friend in 2 minutes?",
            "Which example from class will you remember?",
            "What is still unclear? (Write one question.)",
        ],
        transcript=transcript,
        target_slide_count=metrics.target_slides,
        minutes_per_unit=metrics.minutes_per_unit,
        words_target_slm=metrics.slm_words_per_unit,
        generated_by="template",
        ai_error=None,
    )


def _build_ai_prompt(
    subject: Subject,
    unit: PlannedUnit,
    metrics: UnitMetrics,
    content_slides: int,
    student_friendly: bool,
) -> str:
    style = (
        "STUDENT-FRIENDLY MODE: simplest possible language, many examples, no unexplained jargon."
        if student_friendly
        else "ACADEMIC MODE: professional university tone, still clear."
    )
    return f"""{style}

Course: {subject.name} ({subject.credits} credits)
Unit: {unit.title}

Syllabus for this unit:
{unit.content[:4000] or "Infer topics from the course title and unit number."}

Course-level objectives:
{chr(10).join("- " + o for o in subject.objectives[:6]) or "- Build managerial understanding"}

Create content for Indian university students:

1. introduction (~150 words, welcoming, says what they will learn)
2. learning_objectives: 4 items (Bloom's verbs: Explain, Apply, Analyze, Evaluate)
3. topic_slides: exactly {content_slides} slides. Each slide:
   - title: short (3–6 words)
   - bullets: 3–5 items, max 12 words each, one concept per bullet
   - visual_suggestion: what diagram/image to show
   - speaker_notes: 2–3 simple sentences the teacher says aloud
4. case_study: short scenario students can relate to (India context)
5. summary: 3–4 plain-language takeaways
6. keywords: 8 terms with implied definitions
7. saqs: 3 questions + saq_answers
8. check_your_progress: 3 reflection prompts
9. transcript: ~{metrics.minutes_per_unit} min spoken script, friendly lecturer tone
10. references: 3–5 real or realistic textbooks

JSON schema:
{{
  "introduction": "string",
  "learning_objectives": ["string"],
  "topic_slides": [{{"title": "string", "bullets": ["string"], "visual_suggestion": "string", "speaker_notes": "string"}}],
  "case_study": "string",
  "summary": "string",
  "keywords": ["string"],
  "saqs": ["string"],
  "saq_answers": ["string"],
  "references": ["string"],
  "check_your_progress": ["string"],
  "transcript": "string"
}}"""


def _ai_package(
    subject: Subject,
    unit: PlannedUnit,
    metrics: UnitMetrics,
    config: AIConfig,
    *,
    student_friendly: bool = True,
) -> UnitContentPackage:
    content_slides = max(3, min(15, metrics.target_slides - 6))
    system = STUDENT_SYSTEM if student_friendly else ACADEMIC_SYSTEM
    user = _build_ai_prompt(subject, unit, metrics, content_slides, student_friendly)

    data: dict[str, Any] = chat_json(config, system=system, user=user, temperature=0.55)

    slides = [
        ContentSlide(
            title=s.get("title", "Topic"),
            bullets=[str(b) for b in s.get("bullets", [])[:6]],
            visual_suggestion=str(s.get("visual_suggestion", "")),
            speaker_notes=str(s.get("speaker_notes", "")),
        )
        for s in data.get("topic_slides", [])
    ]
    if len(slides) < 3:
        raise AIClientError("Model returned too few slides")

    return UnitContentPackage(
        unit_title=unit.title,
        introduction=str(data.get("introduction", "")),
        learning_objectives=[str(x) for x in data.get("learning_objectives", [])][:6],
        topic_slides=slides[: content_slides + 2],
        case_study=str(data.get("case_study", "")),
        summary=str(data.get("summary", "")),
        keywords=[str(x) for x in data.get("keywords", [])][:12],
        saqs=[str(x) for x in data.get("saqs", [])][:5],
        saq_answers=[str(x) for x in data.get("saq_answers", [])][:5],
        references=[str(x) for x in data.get("references", DEFAULT_REFERENCES)][:8],
        check_your_progress=[str(x) for x in data.get("check_your_progress", [])][:5],
        transcript=str(data.get("transcript", "")),
        target_slide_count=metrics.target_slides,
        minutes_per_unit=metrics.minutes_per_unit,
        words_target_slm=metrics.slm_words_per_unit,
        generated_by=f"ai:{config.provider}",
        ai_error=None,
    )


def generate_unit_content(
    subject: Subject,
    unit: PlannedUnit,
    unit_count: int,
    *,
    use_ai: bool | None = None,
    api_key: str | None = None,
    model: str | None = None,
    provider: str | None = None,
    base_url: str | None = None,
    student_friendly: bool = True,
) -> UnitContentPackage:
    metrics = compute_unit_metrics(subject.credits, unit_count)
    config = resolve_ai_config(provider=provider, api_key=api_key, model=model, base_url=base_url)
    should_ai = use_ai if use_ai is not None else config is not None

    if should_ai and config:
        try:
            return _ai_package(subject, unit, metrics, config, student_friendly=student_friendly)
        except AIClientError as e:
            pack = _template_package(subject, unit, metrics, student_friendly=student_friendly)
            pack.ai_error = str(e)
            return pack

    pack = _template_package(subject, unit, metrics, student_friendly=student_friendly)
    if should_ai and not config:
        pack.ai_error = "No API key set. Add OPENAI_API_KEY or GROQ_API_KEY to .env or the sidebar."
    return pack
