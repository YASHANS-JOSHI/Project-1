# UGC Course Content Generator

**Main flow:** user enters **subject name** + **syllabus text** (credits, units, topics) → generates unit-wise slides and content pack.

Also supports loading subjects from your local MBA PDF (optional).

| Output | Description |
|--------|-------------|
| **SLM** (`.docx`) | Self-learning material: intro, objectives, topics, case study, SAQs, references |
| **PPT** (`.pptx`) | Expanded unit deck from `Sample PPT (1).pptx` |
| **Transcript** (`.docx`) | Faculty narration (~80 min / unit) |
| **Storyboard** (`.docx`) | Slide-wise visuals and teaching notes |

## Unit rules

| Rule | Behavior |
|------|----------|
| **1** | No PDF units → **units = credits** |
| **3** | PDF Unit I, II, … → use as-is |

## UGC calculations (from your flow doc)

- Learning hours = **credits × 30**
- Slides per unit ≈ **hours per unit × 12** (10–15/hour range)
- SLM words per unit ≈ **(credits × 13,500) ÷ units**
- Transcript aligned to **~80 minutes** per unit

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # optional, for AI
```

### AI mode (recommended for students)

The API rewrites each unit into **simple language**, **short bullets**, **Indian examples**, and a friendly **transcript**.

| Provider | Key | Notes |
|----------|-----|--------|
| **Groq** | `GROQ_API_KEY` | Free tier at [console.groq.com](https://console.groq.com/keys) |
| **OpenAI** | `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com/api-keys) |

```bash
cp .env.example .env
# Add GROQ_API_KEY or OPENAI_API_KEY

python generate.py --subject-name "Marketing Management" \
  --syllabus-file samples/marketing_syllabus_sample.txt --ai --provider groq
```

In Streamlit: sidebar → **Generate slide content with AI** → choose provider → paste API key.

Without a key, the **template engine** still works but bullets stay closer to raw syllabus text.

## Web UI (recommended)

```bash
streamlit run app.py
```

1. Open tab **Custom subject**
2. Enter subject name (e.g. `Marketing Management`)
3. Paste syllabus or upload `.txt` / `.pdf` / `.docx`
4. Click **Preview syllabus**, then **Generate slides & content pack**

Syllabus should include:
- `Credits: 4` (or similar)
- `Unit -I:`, `Unit -II:`, … with topic text

## CLI

```bash
# Custom subject + syllabus file
python generate.py --subject-name "Marketing Management" --syllabus-file my_syllabus.txt

# Optional credit override
python generate.py --subject-name "Operations Research" --syllabus-file syllabus.pdf --credits 3 --ai

# Legacy: list/generate from bundled MBA PDF
python generate.py --list
python generate.py --subject "Marketing Management"
python generate.py --all
```

## Output layout

```
output/MBA_(Online)/Marketing_Management/
  Unit_I/
    Marketing_Management_Unit_I.pptx
    Marketing_Management_Unit_I_SLM.docx
    Marketing_Management_Unit_I_Transcript.docx
    Marketing_Management_Unit_I_Storyboard.docx
  Unit_II/
    ...
```

## Project files

- `MBA-Online (1&2 sem) (2).pdf` — syllabus
- `Sample PPT (1).pptx` — design template
- `FINAL CONTENT DEVELOPMENT FLOW.docx` — full product spec
