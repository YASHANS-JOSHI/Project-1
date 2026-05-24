"""
UGC Course Content Generator — enter subject + syllabus → generate slides & pack.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

# Streamlit Cloud: load API keys from Secrets (see .streamlit/secrets.toml.example)
try:
    if hasattr(st, "secrets"):
        for key in ("GROQ_API_KEY", "GROQ_MODEL", "AI_PROVIDER", "OPENAI_API_KEY", "OPENAI_MODEL"):
            if key in st.secrets:
                os.environ[key] = str(st.secrets[key])
except Exception:
    pass

from ugc_core.custom_syllabus import detect_credits, load_syllabus_file, subject_from_syllabus
from ugc_core.pipeline import export_subject
from ugc_core.syllabus_parser import load_subjects
from ugc_core.unit_planner import plan_units
from ugc_core.ugc_rules import compute_unit_metrics

if not (ROOT / "ugc_core" / "custom_syllabus.py").exists():
    st.error(
        "Missing `ugc_core/` package on the server. "
        "Push the **full** GitHub repo (folder `ugc_core` with all `.py` files), not only `app.py`."
    )
    st.stop()
DEFAULT_PDF = ROOT / "MBA-Online (1&2 sem) (2).pdf"
DEFAULT_TEMPLATE = ROOT / "Sample PPT (1).pptx"
OUTPUT_ROOT = ROOT / "output"

SYLLABUS_PLACEHOLDER = """Course Description:
Brief overview of the subject…

Course Objectives:
• Objective 1
• Objective 2

Course Content:

Unit -I:
Topics for unit one…

Unit -II:
Topics for unit two…

Credits: 4
"""


def _slug(name: str) -> str:
    return re.sub(r"[^\w\-]+", "_", name)[:50].strip("_")


def _sidebar_settings() -> dict:
    st.header("Settings")
    program_name = st.text_input("Program Name", value="MBA (Online)")
    course_code = st.text_input("Course Code prefix", value="MBA")
    delivered_by = st.text_input("Delivered By", value="")
    template_path = st.text_input("PPT template", value=str(DEFAULT_TEMPLATE))

    st.subheader("AI content (recommended)")
    has_key = bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("GROQ_API_KEY"))
    use_ai = st.checkbox(
        "Generate slide content with AI",
        value=has_key,
        help="Clear bullets, examples, and simple language for students.",
    )
    student_friendly = st.checkbox("Student-friendly language", value=True, disabled=not use_ai)

    provider = "openai"
    api_key = ""
    model = ""

    if use_ai:
        provider = st.selectbox(
            "API provider",
            ["openai", "groq"],
            index=1 if os.environ.get("GROQ_API_KEY") and not os.environ.get("OPENAI_API_KEY") else 0,
            help="Groq has a free tier and works well for drafts.",
        )
        if provider == "groq":
            api_key = st.text_input("GROQ_API_KEY", type="password", value=os.environ.get("GROQ_API_KEY", ""))
            model = st.text_input("Model", value=os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"))
            if api_key:
                os.environ["GROQ_API_KEY"] = api_key
                os.environ["AI_PROVIDER"] = "groq"
            if model:
                os.environ["GROQ_MODEL"] = model
        else:
            api_key = st.text_input("OPENAI_API_KEY", type="password", value=os.environ.get("OPENAI_API_KEY", ""))
            model = st.text_input("Model", value=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"))
            if api_key:
                os.environ["OPENAI_API_KEY"] = api_key
                os.environ["AI_PROVIDER"] = "openai"
            if model:
                os.environ["OPENAI_MODEL"] = model

        st.caption(
            "Get keys: [OpenAI](https://platform.openai.com/api-keys) · "
            "[Groq](https://console.groq.com/keys) (free tier)"
        )

    include_storyboard = st.checkbox("Include storyboard", value=True)
    return {
        "program_name": program_name,
        "course_code": course_code,
        "delivered_by": delivered_by,
        "template_path": template_path,
        "use_ai": use_ai,
        "student_friendly": student_friendly,
        "provider": provider if use_ai else None,
        "api_key": api_key if use_ai else None,
        "model": model if use_ai else None,
        "include_storyboard": include_storyboard,
    }


def _render_preview(subject, units, metrics) -> None:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Credits", subject.credits)
    c2.metric("Units", len(units))
    c3.metric("Slides / unit (target)", metrics.target_slides)
    c4.metric("SLM words / unit", f"{metrics.slm_words_per_unit:,}")
    src = units[0].source.upper() if units else "—"
    st.caption(f"Units from: **{src}** (PDF/syllabus text = units listed · otherwise credits = unit count)")

    for u in units:
        with st.expander(f"Unit {u.label}"):
            st.write(u.content[:2000] if u.content else "_No unit text — generator will use credits/AI._")
            if u.topics:
                for t in u.topics[:6]:
                    st.write(f"- {t[:180]}")


def _run_generation(subject, settings: dict) -> None:
    tpl = Path(settings["template_path"])
    if not tpl.exists():
        st.error(f"Template not found: {tpl}")
        return
    out_dir = OUTPUT_ROOT / _slug(settings["program_name"]) / _slug(subject.name)
    mode = "AI" if settings["use_ai"] else "template"
    with st.spinner(f"Generating {subject.name} ({mode})…"):
        result = export_subject(
            subject,
            out_dir,
            tpl,
            program_name=settings["program_name"],
            course_code=f"{settings['course_code']}-{_slug(subject.name)[:15]}",
            delivered_by=settings["delivered_by"],
            use_ai=settings["use_ai"],
            include_storyboard=settings["include_storyboard"],
            student_friendly=settings.get("student_friendly", True),
            api_key=settings.get("api_key") or None,
            model=settings.get("model") or None,
            provider=settings.get("provider"),
        )
    files: list[str] = []
    for b in result.units:
        if b.pack.ai_error:
            st.warning(f"Unit {b.unit.label}: AI unavailable — used template. ({b.pack.ai_error})")
        elif settings["use_ai"]:
            st.caption(f"Unit {b.unit.label}: content via **{b.pack.generated_by}**")
        for p in (b.ppt, b.slm, b.transcript, b.storyboard):
            if p:
                files.append(str(p))
    st.success(f"Generated {len(files)} files in `{out_dir}`")
    for f in files:
        st.code(f)


def tab_custom_subject(settings: dict) -> None:
    st.subheader("Enter subject & syllabus")
    st.write(
        "Paste or upload the **subject syllabus** (credits, units, topics). "
        "The app detects **Credits: N** and **Unit I / Unit -II** sections, then builds slides."
    )

    subject_name = st.text_input("Subject name", placeholder="e.g. Marketing Management")
    col_a, col_b = st.columns([2, 1])
    with col_a:
        syllabus_text = st.text_area(
            "Syllabus text",
            height=320,
            placeholder=SYLLABUS_PLACEHOLDER,
            help="Include units (Unit -I:, Unit II:, …) and credits if possible.",
        )
    with col_b:
        uploaded = st.file_uploader("Or upload syllabus", type=["txt", "pdf", "docx"])
        credits_override = st.number_input(
            "Credits (optional override)",
            min_value=0,
            max_value=10,
            value=0,
            step=1,
            help="Leave at 0 to auto-detect from syllabus (e.g. Credits: 4).",
        )

    if uploaded:
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(uploaded.name).suffix) as tmp:
            tmp.write(uploaded.getvalue())
            tmp_path = Path(tmp.name)
        try:
            st.session_state["uploaded_syllabus"] = load_syllabus_file(tmp_path)
            st.caption(f"Loaded **{uploaded.name}** ({len(st.session_state['uploaded_syllabus']):,} chars)")
        finally:
            tmp_path.unlink(missing_ok=True)

    combined_text = (syllabus_text or "").strip() or st.session_state.get("uploaded_syllabus", "")
    if combined_text:
        detected = detect_credits(combined_text)
        if detected:
            st.info(f"Detected credits in syllabus: **{detected}**")
        elif credits_override == 0:
            st.warning("No credits found in text — set credits manually or add a line like `Credits: 4`.")

    if st.button("Preview syllabus", type="secondary"):
        if not subject_name or not combined_text.strip():
            st.error("Enter subject name and syllabus text.")
            return
        try:
            cr = int(credits_override) if credits_override > 0 else None
            subject = subject_from_syllabus(subject_name, combined_text, credits=cr)
            st.session_state["custom_subject"] = subject
        except Exception as e:
            st.error(str(e))

    subject = st.session_state.get("custom_subject")
    if subject and subject.name == subject_name:
        units = plan_units(subject)
        metrics = compute_unit_metrics(subject.credits, len(units))
        _render_preview(subject, units, metrics)

        if st.button("Generate slides & content pack", type="primary"):
            _run_generation(subject, settings)


def tab_mba_pdf(settings: dict) -> None:
    st.subheader("Load from MBA PDF (optional)")
    pdf_path = st.text_input("Syllabus PDF path", value=str(DEFAULT_PDF))
    if st.button("Load subjects from PDF"):
        try:
            st.session_state["pdf_subjects"] = load_subjects(Path(pdf_path))
        except Exception as e:
            st.error(str(e))

    subjects = st.session_state.get("pdf_subjects", [])
    if not subjects:
        st.caption("Uses your local `MBA-Online` PDF if you already have it.")
        return

    selected = st.selectbox("Subject", [s.name for s in subjects])
    subject = next(s for s in subjects if s.name == selected)
    units = plan_units(subject)
    metrics = compute_unit_metrics(subject.credits, len(units))
    _render_preview(subject, units, metrics)

    if st.button("Generate from PDF subject", type="primary"):
        _run_generation(subject, settings)


def main() -> None:
    st.set_page_config(page_title="UGC Content Generator", layout="wide")
    st.title("UGC Course Content Generator")
    st.caption("Enter subject + syllabus → unit-wise PPT, SLM, transcript")

    with st.sidebar:
        settings = _sidebar_settings()

    tab_custom, tab_pdf = st.tabs(["Custom subject", "From MBA PDF"])

    with tab_custom:
        tab_custom_subject(settings)
    with tab_pdf:
        tab_mba_pdf(settings)


if __name__ == "__main__":
    main()
