"""CLI: full UGC content pack (SLM + PPT + transcript + storyboard)."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.custom_syllabus import load_syllabus_file, subject_from_syllabus
from src.pipeline import export_subject
from src.syllabus_parser import load_subjects
from src.unit_planner import plan_units
from src.ugc_rules import compute_unit_metrics

ROOT = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser(description="UGC unit content pack generator")
    parser.add_argument("--pdf", type=Path, default=ROOT / "MBA-Online (1&2 sem) (2).pdf")
    parser.add_argument("--template", type=Path, default=ROOT / "Sample PPT (1).pptx")
    parser.add_argument("--program", default="MBA (Online)")
    parser.add_argument("--code", default="MBA")
    parser.add_argument("--subject", help="Subject name (partial match, PDF mode)")
    parser.add_argument("--subject-name", help="Custom mode: exact subject title")
    parser.add_argument("--syllabus-file", type=Path, help="Custom mode: syllabus .txt/.pdf/.docx")
    parser.add_argument("--syllabus-text", type=Path, help="Custom mode: plain text file (alias)")
    parser.add_argument("--credits", type=int, help="Override credits (custom mode)")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--ai", action="store_true", help="Use LLM API (OPENAI_API_KEY or GROQ_API_KEY)")
    parser.add_argument("--provider", choices=["openai", "groq"], help="AI provider (default: openai or env)")
    parser.add_argument("--no-storyboard", action="store_true")
    parser.add_argument(
        "--no-student-friendly",
        action="store_true",
        help="Use formal academic tone instead of simplified student language",
    )
    args = parser.parse_args()

    # Custom: subject name + syllabus file
    if args.subject_name:
        syllabus_path = args.syllabus_file or args.syllabus_text
        if not syllabus_path or not syllabus_path.exists():
            raise SystemExit("Custom mode requires --syllabus-file (or --syllabus-text) pointing to a file.")
        text = load_syllabus_file(syllabus_path)
        subj = subject_from_syllabus(args.subject_name, text, credits=args.credits)
        out = ROOT / "output" / args.program.replace(" ", "_") / subj.name.replace(" ", "_")
        result = export_subject(
            subj,
            out,
            args.template,
            program_name=args.program,
            course_code=f"{args.code}-{subj.name[:12].replace(' ', '')}",
            use_ai=args.ai if args.ai else None,
            include_storyboard=not args.no_storyboard,
            student_friendly=not args.no_student_friendly,
            provider=args.provider,
        )
        print(f"{subj.name} ({subj.credits} cr, {len(result.units)} units) -> {out}")
        for b in result.units:
            eng = b.pack.generated_by
            if b.pack.ai_error:
                print(f"  Unit {b.unit.label}: template (AI failed: {b.pack.ai_error})")
            else:
                print(f"  Unit {b.unit.label}: {eng} -> {b.ppt}")
        return

    subjects = load_subjects(args.pdf)
    if args.list or (not args.subject and not args.all):
        print(f"Parsed {len(subjects)} subjects:\n")
        for s in subjects:
            u = plan_units(s)
            m = compute_unit_metrics(s.credits, len(u))
            print(
                f"  - {s.name} ({s.credits} cr, {len(u)} units, "
                f"~{m.target_slides} slides/unit, ~{m.slm_words_per_unit:,} SLM words/unit)"
            )
        return

    if args.all:
        targets = subjects
    else:
        key = (args.subject or "").lower()
        targets = [s for s in subjects if key in s.name.lower()]
        if not targets:
            raise SystemExit(f"No subject matching: {args.subject}")

    for subj in targets:
        out = ROOT / "output" / args.program.replace(" ", "_") / subj.name.replace(" ", "_")
        result = export_subject(
            subj,
            out,
            args.template,
            program_name=args.program,
            course_code=f"{args.code}-{subj.name[:12].replace(' ', '')}",
            use_ai=args.ai if args.ai else None,
            include_storyboard=not args.no_storyboard,
            student_friendly=not args.no_student_friendly,
            provider=args.provider,
        )
        print(f"\n{subj.name} -> {out}")
        for bundle in result.units:
            print(
                f"  Unit {bundle.unit.label}: "
                f"{bundle.pack.target_slide_count} slides target, "
                f"engine={bundle.pack.generated_by}"
            )
            print(f"    PPT: {bundle.ppt}")
            print(f"    SLM: {bundle.slm}")
            print(f"    Transcript: {bundle.transcript}")
            if bundle.storyboard:
                print(f"    Storyboard: {bundle.storyboard}")


if __name__ == "__main__":
    main()
