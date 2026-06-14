"""
output_agent.py — formats raw research reports into different output styles.
Also generates presentation-ready slide content for PPTX export.
"""

import os
import re
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

MODEL  = "llama-3.1-8b-instant"


def get_client() -> Groq:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set. Add it to backend/.env to use AI generation endpoints.")
    return Groq(api_key=api_key)


class OutputAgent:
    """Reformats a raw research report into one of four output styles."""

    STYLES = {
        "Research Paper": """
Reformat the report as a highly comprehensive, detailed, and long-form academic research paper with these sections:
# Abstract
# 1. Introduction
# 2. Background and Context
# 3. Methodology & Literature Review
# 4. Key Findings (in-depth analysis with all available data)
# 5. Implications & Discussion
# 6. Conclusion
# References

Use highly professional academic language. Expand on all points to ensure maximum detail and length. Keep all factual content from the original.
Do NOT add placeholder text like "research data and statistics" — use the actual data. Aim for a long, thorough paper.
""",
        "Executive Summary": """
Reformat as a concise executive summary (max 400 words):
# Executive Summary: [Topic]
## Situation
## Key Findings (3-5 bullet points with specific data/numbers)
## Implications
## Recommended Actions

Be specific — include actual statistics and findings, no vague placeholders.
""",
        "Literature Review": """
Reformat as an academic literature review:
# Literature Review: [Topic]
## 1. Overview of Existing Research
## 2. Major Themes & Trends
## 3. Key Studies and Findings
## 4. Gaps in Current Research
## 5. Future Directions

Synthesise the research and cite specific findings where available.
""",
        "Presentation": """
Reformat as presentation slide content. Create 6-8 slides using EXACTLY this format:

SLIDE 1: [Descriptive title — NOT "Introduction"]
- [Specific, concrete bullet point — include actual data/numbers if available]
- [Specific, concrete bullet point]
- [Specific, concrete bullet point]

SLIDE 2: [Descriptive title]
- [Specific bullet]
- [Specific bullet]
- [Specific bullet]

Rules:
- Each slide title must describe its SPECIFIC content (e.g. "Generative AI Adoption: 75% of Enterprises" NOT "Key Finding #1")
- Each bullet must contain real information from the report — NO placeholder text
- Never write "Supporting evidence: research data" — write the actual evidence
- Never write "Thank you message" — that is added automatically
- Never write "Slide N" as a title — use descriptive titles
- 3-5 bullets per slide, each a complete thought
- Include specific statistics, percentages, company names, dates when available
- NEVER mention technical issues, data fetching errors, API problems, or unavailable data
- NEVER write anything like "data could not be retrieved", "technical difficulties", or "error"
- If specific data is limited, use what IS available in the report and present it confidently
"""
    }

    def format_report(self, report: str, topic: str, style: str) -> str:
        """Return the report reformatted in the requested style."""
        system_prompt = self.STYLES.get(style, self.STYLES["Research Paper"])

        prompt = f"""
You are a professional document formatter.

Topic: {topic}
Output style: {style}

{system_prompt}

--- ORIGINAL REPORT ---
{report}
--- END REPORT ---

Produce ONLY the formatted output. No preamble, no meta-commentary.
"""
        max_tokens_val = 6000 if style == "Research Paper" else 2000
        
        response = get_client().chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens_val,
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()


_ERROR_PATTERNS = [
    r'technical.{0,30}(issue|problem|error|difficult)',
    r'(could not|unable to|failed to).{0,40}(fetch|retrieve|access|load|get)',
    r'data.{0,30}(unavailable|not available|missing|not found)',
    r'(api|service|network).{0,30}(error|fail|timeout|down)',
    r'error.{0,30}(occurred|encounter|happen)',
    r'(fetch|retriev).{0,30}(error|fail)',
    r'(sorry|apolog).{0,40}(data|info|content)',
    r'(data|information).{0,30}(could not|cannot).{0,20}(be|was).{0,20}(obtain|retriev|fetch|load)',
]


def _is_error_slide(title: str, bullets: list) -> bool:
    """Return True if a slide appears to be about technical/fetch errors."""
    import re as _re
    combined = (title + ' ' + ' '.join(bullets)).lower()
    for pat in _ERROR_PATTERNS:
        if _re.search(pat, combined, _re.IGNORECASE):
            return True
    return False


def _sanitise_slide_text(raw: str) -> str:
    """
    Remove any slide blocks that talk about technical errors or data-fetch issues.
    Works on the raw LLM output before it reaches the PPTX builder.
    """
    import re as _re
    lines = raw.split('\n')
    cleaned_blocks = []
    current_block_lines = []
    current_title = ''
    current_bullets = []

    def flush():
        nonlocal current_block_lines, current_title, current_bullets
        if current_title and not _is_error_slide(current_title, current_bullets):
            cleaned_blocks.extend(current_block_lines)
        current_block_lines = []
        current_title = ''
        current_bullets = []

    for line in lines:
        m = _re.match(r'^SLIDE\s+\d+[:.]?\s*(.*)', line.strip(), _re.IGNORECASE)
        if m:
            flush()
            current_title = m.group(1).strip()
            current_block_lines = [line]
        else:
            current_block_lines.append(line)
            bm = _re.match(r'^[-*•]\s+(.*)', line.strip())
            if bm:
                current_bullets.append(bm.group(1).strip())
            elif line.strip() and current_title:
                # Plain text line in a slide — treat as implicit bullet for filtering
                current_bullets.append(line.strip())

    flush()

    # Re-number slides sequentially
    result_lines = []
    slide_counter = 0
    for line in cleaned_blocks:
        if _re.match(r'^SLIDE\s+\d+', line.strip(), _re.IGNORECASE):
            slide_counter += 1
            # Replace the slide number with sequential one
            new_line = _re.sub(r'^SLIDE\s+\d+', f'SLIDE {slide_counter}', line.strip(), flags=_re.IGNORECASE)
            result_lines.append(new_line)
        else:
            result_lines.append(line)

    return '\n'.join(result_lines)


def generate_presentation(topic: str, report: str) -> str:
    """
    Generate structured slide content from a research report.
    Returns text in the SLIDE N: format for the PPTX builder.
    """
    # Trim excessively long reports to stay within token limits cleanly
    report_trimmed = report[:8000] if len(report) > 8000 else report

    prompt = f"""You are a professional research analyst creating a comprehensive PowerPoint presentation on: \"{topic}\"

Generate exactly 10 content slides from the research report below.
Use EXACTLY this format — no deviations, one blank line between slides:

SLIDE 1: [Specific, descriptive title]
- [Full informative sentence with data/fact from the report]
- [Full informative sentence with data/fact]
- [Full informative sentence with data/fact]
- [Full informative sentence with data/fact]
- [Full informative sentence with data/fact]

SLIDE 2: [Specific, descriptive title]
- [Full informative sentence]
- [Full informative sentence]
- [Full informative sentence]
- [Full informative sentence]
- [Full informative sentence]

[continue identically for SLIDE 3 through SLIDE 10]

CRITICAL CONTENT RULES — every rule must be followed:
1. Slide titles MUST be SPECIFIC and topically meaningful.
   GOOD: "Global AI Market: $200B Valuation and 38% Annual Growth"
   BAD: "Key Finding", "Overview", "Introduction", "Slide 2"

2. Each bullet MUST be a complete, standalone, informative sentence — not a fragment.
   GOOD: "Large language models like GPT-4 demonstrated 86% accuracy on medical diagnosis benchmarks in 2024."
   BAD: "High accuracy on benchmarks" or "GPT-4 results"

3. Each slide MUST have exactly 5 bullets (not fewer). If the report has rich data on a topic, expand to 6-7 bullets.

4. Include specific numbers, percentages, years, named entities, and direct quotes wherever the report provides them.

5. The 10 slides MUST cover all of these angles (one slide each):
   - Background & context of the field
   - Current state / scale of the domain
   - Key finding or theme #1
   - Key finding or theme #2
   - Key finding or theme #3
   - Key finding or theme #4
   - Comparative analysis or competing approaches
   - Challenges & limitations
   - Real-world applications & case studies
   - Future outlook & emerging directions

6. ABSOLUTELY FORBIDDEN:
   - Technical/API errors, data fetch failures, "could not retrieve", "unavailable"
   - Placeholder text of any kind
   - "Thank you", "Questions?", "References", "Q&A"
   - Slide numbers inside titles
   - Vague, generic statements with no factual grounding

7. Write each bullet as a dense, informative sentence (20-40 words ideally).
   Extract every relevant fact, stat, trend, name, and date from the report.

--- RESEARCH REPORT ---
{report_trimmed}
--- END REPORT ---

Output ONLY the 10 slides in the SLIDE N: format above. No preamble, no commentary."""

    response = get_client().chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=4500,
        temperature=0.15,
    )
    raw = response.choices[0].message.content.strip()
    return _sanitise_slide_text(raw)
    
    # ── Backwards-compatible aliases (used by ui/app.py) ─────────────────────────

def generate_research_paper(topic: str, report: str) -> str:
    return OutputAgent().format_report(report, topic, "Research Paper")

def generate_executive_summary(topic: str, report: str) -> str:
    return OutputAgent().format_report(report, topic, "Executive Summary")

def generate_literature_review(topic: str, report: str) -> str:
    return OutputAgent().format_report(report, topic, "Literature Review")

def save_output(topic: str, content: str, format_type: str) -> str:
    import datetime, re, os
    safe  = re.sub(r'[^a-zA-Z0-9_]', '_', topic)[:40]
    fmt   = format_type.upper().replace(' ', '_')
    ts    = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    fname = f"reports/{ts}_{fmt}_{safe}.txt"
    os.makedirs("reports", exist_ok=True)
    with open(fname, 'w', encoding='utf-8') as f:
        f.write(content)
    return fname
