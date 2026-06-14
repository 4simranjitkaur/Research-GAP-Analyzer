"""
paper_analyzer_agent.py
========================
Handles three core tasks for uploaded research PDFs:
  1. Text extraction from PDF bytes (PyMuPDF)
  2. Structured paper analysis (summary, contributions, limitations)
  3. Novelty Score (0-10) — compared against live ArXiv results
  4. Gap Analysis + Gap Score (0-10) — identifies research gaps with severity
"""

import os
import re
import time
import json
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

MODEL = "llama-3.1-8b-instant"


def get_client() -> Groq:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set. Add it to backend/.env to analyze papers.")
    return Groq(api_key=api_key)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _llm(prompt: str, system: str = "", temperature: float = 0.2, max_tokens: int = 2048) -> str:
    """Groq LLM call with retry on rate-limit."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    for attempt in range(3):
        try:
            resp = get_client().chat.completions.create(
                model=MODEL,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            if "429" in str(e) or "rate_limit" in str(e).lower():
                wait = 60 * (attempt + 1)
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("LLM failed after 3 retries")


def _fetch_arxiv(query: str, max_results: int = 6) -> str:
    """Live ArXiv API call — returns raw titles + abstracts as a single string."""
    try:
        encoded = urllib.parse.quote(query)
        url = (
            f"http://export.arxiv.org/api/query"
            f"?search_query=all:{encoded}"
            f"&start=0&max_results={max_results}"
            f"&sortBy=submittedDate&sortOrder=descending"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "ResearchAnalyzer/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            xml_data = resp.read()

        root = ET.fromstring(xml_data)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entries = root.findall("atom:entry", ns)

        parts = []
        for entry in entries:
            title = entry.find("atom:title", ns).text.strip().replace("\n", " ")
            abstract = entry.find("atom:summary", ns).text.strip().replace("\n", " ")[:400]
            authors = [a.find("atom:name", ns).text for a in entry.findall("atom:author", ns)][:3]
            parts.append(f"Title: {title}\nAuthors: {', '.join(authors)}\nAbstract: {abstract}")

        return "\n\n---\n\n".join(parts) if parts else "No recent ArXiv papers found."
    except Exception as e:
        return f"ArXiv fetch failed: {str(e)}"


# ─────────────────────────────────────────────────────────────────────────────
# 1. PDF TEXT EXTRACTION
# ─────────────────────────────────────────────────────────────────────────────

def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """
    Extract readable text from uploaded PDF bytes using PyMuPDF.
    Returns combined text from first 15 pages (enough for analysis).
    """
    try:
        import fitz  # PyMuPDF
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        doc = fitz.open(tmp_path)
        pages_text = []
        for i, page in enumerate(doc):
            if i >= 15:
                break
            text = page.get_text().strip()
            if text:
                pages_text.append(f"[Page {i+1}]\n{text}")

        doc.close()
        os.unlink(tmp_path)

        full_text = "\n\n".join(pages_text)
        return full_text if full_text.strip() else "Could not extract readable text from this PDF."
    except Exception as e:
        return f"PDF extraction error: {str(e)}"


# ─────────────────────────────────────────────────────────────────────────────
# 2. PAPER ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────

def analyze_paper(pdf_text: str, log_callback=None) -> dict:
    """
    Full structured analysis of a research paper.
    Returns: title, authors, domain, summary, methodology, contributions, limitations, keywords
    """
    if log_callback:
        log_callback("📄 Analyzing paper structure and content...")

    truncated = pdf_text[:5000]

    prompt = f"""You are an expert research analyst. Analyze the research paper below and extract structured information.

PAPER TEXT:
{truncated}

Respond in EXACTLY this format (use the labels as shown):

TITLE: [Paper title, or "Unknown" if not found]
AUTHORS: [Comma-separated authors, or "Unknown"]
DOMAIN: [Research domain/field, e.g. "Computer Vision", "NLP", "Quantum Computing"]
KEYWORDS: [5-8 key terms from the paper, comma-separated]

SUMMARY:
[2-3 sentence plain-English summary of what this paper is about and what it achieves]

METHODOLOGY:
[2-3 sentences describing the research approach, techniques, datasets, or experiments used]

KEY_CONTRIBUTIONS:
- [Contribution 1 — specific and concrete]
- [Contribution 2 — specific and concrete]
- [Contribution 3 — specific and concrete]
- [Contribution 4, if applicable]

LIMITATIONS:
- [Limitation 1 acknowledged in the paper or evident from reading]
- [Limitation 2]
- [Limitation 3, if applicable]

Only use information from the paper text. Do not fabricate details."""

    raw = _llm(prompt, system="You are a precise, factual research paper analyst.", max_tokens=1500)

    # Parse the structured response
    result = {
        "title": "Unknown",
        "authors": "Unknown",
        "domain": "Unknown",
        "keywords": [],
        "summary": "",
        "methodology": "",
        "contributions": [],
        "limitations": [],
        "raw": raw,
    }

    current_key = None
    buffer = []

    for line in raw.split("\n"):
        line_stripped = line.strip()
        if line_stripped.startswith("TITLE:"):
            result["title"] = line_stripped.split(":", 1)[1].strip()
        elif line_stripped.startswith("AUTHORS:"):
            result["authors"] = line_stripped.split(":", 1)[1].strip()
        elif line_stripped.startswith("DOMAIN:"):
            result["domain"] = line_stripped.split(":", 1)[1].strip()
        elif line_stripped.startswith("KEYWORDS:"):
            kws = line_stripped.split(":", 1)[1].strip()
            result["keywords"] = [k.strip() for k in kws.split(",") if k.strip()]
        elif line_stripped == "SUMMARY:":
            current_key = "summary"
            buffer = []
        elif line_stripped == "METHODOLOGY:":
            if current_key == "summary":
                result["summary"] = " ".join(buffer).strip()
            current_key = "methodology"
            buffer = []
        elif line_stripped == "KEY_CONTRIBUTIONS:":
            if current_key == "methodology":
                result["methodology"] = " ".join(buffer).strip()
            current_key = "contributions"
            buffer = []
        elif line_stripped == "LIMITATIONS:":
            if current_key == "contributions":
                result["contributions"] = [b.lstrip("- •").strip() for b in buffer if b.strip()]
            current_key = "limitations"
            buffer = []
        elif current_key:
            if line_stripped:
                buffer.append(line_stripped)

    # Flush last buffer
    if current_key == "limitations":
        result["limitations"] = [b.lstrip("- •").strip() for b in buffer if b.strip()]
    elif current_key == "summary" and not result["summary"]:
        result["summary"] = " ".join(buffer).strip()

    if log_callback:
        log_callback(f"✅ Paper analysis complete — domain: {result['domain']}")

    return result


# ─────────────────────────────────────────────────────────────────────────────
# 3. NOVELTY SCORE (Live ArXiv comparison)
# ─────────────────────────────────────────────────────────────────────────────

def compute_novelty_score(pdf_text: str, topic: str, log_callback=None) -> dict:
    """
    Scores the novelty of a research paper (0-10) by:
      1. Fetching the latest ArXiv papers on the same topic (live)
      2. Asking the LLM to compare and score across three dimensions

    Returns:
      overall_score, originality, methodology_innovation, practical_contribution,
      justification, similar_papers, strengths, weaknesses
    """
    if log_callback:
        log_callback(f"🔍 Fetching live ArXiv papers on: '{topic}'...")

    arxiv_context = _fetch_arxiv(topic, max_results=6)

    if log_callback:
        log_callback("🧠 Comparing paper against ArXiv literature for novelty...")

    paper_excerpt = pdf_text[:4000]

    prompt = f"""You are an expert academic reviewer evaluating the novelty of a research paper.

PAPER UNDER REVIEW (excerpt):
{paper_excerpt}

RECENT ARXIV PAPERS ON THE SAME TOPIC:
{arxiv_context[:3000]}

Score the paper's novelty on THREE dimensions (each 0-10):
1. ORIGINALITY — how new/unique is the core idea compared to existing ArXiv work?
2. METHODOLOGY_INNOVATION — does it use a new/improved technique or approach?
3. PRACTICAL_CONTRIBUTION — does it advance real-world applicability or benchmarks?

Also identify up to 3 similar ArXiv papers that are most closely related.

Respond in EXACTLY this format:

OVERALL_SCORE: [single integer 0-10]
ORIGINALITY: [integer 0-10]
METHODOLOGY_INNOVATION: [integer 0-10]
PRACTICAL_CONTRIBUTION: [integer 0-10]

JUSTIFICATION:
[3-5 sentences explaining the overall novelty assessment, referencing specific differences from ArXiv papers]

STRENGTHS:
- [Novel strength 1]
- [Novel strength 2]
- [Novel strength 3]

WEAKNESSES:
- [Novelty weakness 1 — what has already been done]
- [Novelty weakness 2]

SIMILAR_PAPERS:
- [Title of most similar ArXiv paper]
- [Title of second similar paper]
- [Title of third similar paper, if applicable]"""

    raw = _llm(prompt, system="You are a rigorous, fair academic novelty reviewer.", max_tokens=1200)

    result = {
        "overall_score": 5,
        "originality": 5,
        "methodology_innovation": 5,
        "practical_contribution": 5,
        "justification": "",
        "strengths": [],
        "weaknesses": [],
        "similar_papers": [],
        "raw": raw,
    }

    current_key = None
    buffer = []

    for line in raw.split("\n"):
        s = line.strip()
        if s.startswith("OVERALL_SCORE:"):
            try:
                result["overall_score"] = int(re.search(r"\d+", s.split(":", 1)[1]).group())
            except:
                pass
        elif s.startswith("ORIGINALITY:"):
            try:
                result["originality"] = int(re.search(r"\d+", s.split(":", 1)[1]).group())
            except:
                pass
        elif s.startswith("METHODOLOGY_INNOVATION:"):
            try:
                result["methodology_innovation"] = int(re.search(r"\d+", s.split(":", 1)[1]).group())
            except:
                pass
        elif s.startswith("PRACTICAL_CONTRIBUTION:"):
            try:
                result["practical_contribution"] = int(re.search(r"\d+", s.split(":", 1)[1]).group())
            except:
                pass
        elif s == "JUSTIFICATION:":
            current_key = "justification"
            buffer = []
        elif s == "STRENGTHS:":
            if current_key == "justification":
                result["justification"] = " ".join(buffer).strip()
            current_key = "strengths"
            buffer = []
        elif s == "WEAKNESSES:":
            if current_key == "strengths":
                result["strengths"] = [b.lstrip("- •").strip() for b in buffer if b.strip()]
            current_key = "weaknesses"
            buffer = []
        elif s == "SIMILAR_PAPERS:":
            if current_key == "weaknesses":
                result["weaknesses"] = [b.lstrip("- •").strip() for b in buffer if b.strip()]
            current_key = "similar_papers"
            buffer = []
        elif current_key:
            if s:
                buffer.append(s)

    # Flush last buffer
    if current_key == "similar_papers":
        result["similar_papers"] = [b.lstrip("- •").strip() for b in buffer if b.strip()]
    elif current_key == "justification" and not result["justification"]:
        result["justification"] = " ".join(buffer).strip()

    # Clamp all scores to 0-10
    for key in ["overall_score", "originality", "methodology_innovation", "practical_contribution"]:
        result[key] = max(0, min(10, result[key]))

    if log_callback:
        log_callback(f"🏆 Novelty Score: {result['overall_score']}/10")

    return result


# ─────────────────────────────────────────────────────────────────────────────
# 4. GAP ANALYSIS + GAP SCORE
# ─────────────────────────────────────────────────────────────────────────────

def compute_gap_analysis(pdf_text: str, topic: str, log_callback=None) -> dict:
    """
    Identifies research gaps in the paper and computes a Gap Score (0-10).
    Higher gap score = more significant unaddressed research opportunities.

    Returns:
      gap_score, gaps (list of {description, severity, category}),
      future_directions, summary
    """
    if log_callback:
        log_callback("🔬 Performing gap analysis on the paper...")

    paper_excerpt = pdf_text[:4500]

    prompt = f"""You are an expert research gap analyst. Analyze this research paper and identify specific, actionable research gaps.

PAPER TEXT:
{paper_excerpt}

RESEARCH TOPIC: {topic}

Identify 4-7 specific research gaps. For each gap, assign:
- SEVERITY: High / Medium / Low
- CATEGORY: one of: Methodology | Dataset | Scalability | Evaluation | Application | Theory | Reproducibility | Ethics

Also compute an overall GAP_SCORE (0-10):
  - 0-3 = Paper is comprehensive, few gaps remain
  - 4-6 = Moderate gaps, some clear directions for future work
  - 7-10 = Significant gaps, major research opportunities remain

Respond in EXACTLY this format:

GAP_SCORE: [integer 0-10]

GAP_SUMMARY:
[2-3 sentences summarizing the overall gap landscape of this paper]

GAPS:
GAP_1:
DESCRIPTION: [Specific, actionable gap description — not vague]
SEVERITY: [High/Medium/Low]
CATEGORY: [one category from the list above]

GAP_2:
DESCRIPTION: [...]
SEVERITY: [...]
CATEGORY: [...]

GAP_3:
DESCRIPTION: [...]
SEVERITY: [...]
CATEGORY: [...]

GAP_4:
DESCRIPTION: [...]
SEVERITY: [...]
CATEGORY: [...]

GAP_5:
DESCRIPTION: [...]
SEVERITY: [...]
CATEGORY: [...]

FUTURE_DIRECTIONS:
- [Specific future research direction 1]
- [Specific future research direction 2]
- [Specific future research direction 3]
- [Specific future research direction 4]

Only use information grounded in the paper. Be specific and concrete — avoid generic statements."""

    raw = _llm(prompt, system="You are a precise and insightful research gap analyst.", max_tokens=1500)

    result = {
        "gap_score": 5,
        "summary": "",
        "gaps": [],
        "future_directions": [],
        "raw": raw,
    }

    # Parse gap_score
    score_match = re.search(r"GAP_SCORE:\s*(\d+)", raw)
    if score_match:
        result["gap_score"] = max(0, min(10, int(score_match.group(1))))

    # Parse summary
    summary_match = re.search(r"GAP_SUMMARY:\s*\n(.*?)(?=\nGAPS:|\nGAP_1:)", raw, re.DOTALL)
    if summary_match:
        result["summary"] = summary_match.group(1).strip()

    # Parse individual gaps
    gap_blocks = re.findall(
        r"GAP_\d+:\s*\nDESCRIPTION:\s*(.*?)\nSEVERITY:\s*(High|Medium|Low)\s*\nCATEGORY:\s*(\w+)",
        raw,
        re.DOTALL | re.IGNORECASE
    )
    for desc, severity, category in gap_blocks:
        result["gaps"].append({
            "description": desc.strip(),
            "severity": severity.strip().capitalize(),
            "category": category.strip().capitalize(),
        })

    # Parse future directions
    fd_match = re.search(r"FUTURE_DIRECTIONS:\s*\n(.*?)$", raw, re.DOTALL)
    if fd_match:
        lines = fd_match.group(1).strip().split("\n")
        result["future_directions"] = [
            l.lstrip("- •0123456789.").strip()
            for l in lines if l.strip() and not l.strip().startswith("GAP")
        ]

    if log_callback:
        log_callback(f"🔍 Gap Score: {result['gap_score']}/10 — {len(result['gaps'])} gaps identified")

    return result


# ─────────────────────────────────────────────────────────────────────────────
# 5. FULL PIPELINE (single paper)
# ─────────────────────────────────────────────────────────────────────────────

def run_full_paper_analysis(pdf_bytes: bytes, topic_hint: str = "", log_callback=None) -> dict:
    """
    Master function: extract → analyze → novelty score → gap analysis.
    Returns a consolidated dict with all results.
    """
    if log_callback:
        log_callback("📥 Extracting text from PDF...")

    pdf_text = extract_text_from_pdf_bytes(pdf_bytes)

    if "extraction error" in pdf_text.lower() or len(pdf_text.strip()) < 200:
        return {"error": pdf_text or "Could not extract enough text from the PDF."}

    # Step 1: Analyze paper
    analysis = analyze_paper(pdf_text, log_callback=log_callback)

    # Derive topic from paper if not provided
    topic = topic_hint.strip() if topic_hint.strip() else analysis.get("domain", "machine learning")
    if analysis.get("keywords"):
        topic = f"{topic} {' '.join(analysis['keywords'][:3])}"

    # Step 2: Novelty score
    novelty = compute_novelty_score(pdf_text, topic, log_callback=log_callback)

    # Step 3: Gap analysis
    gaps = compute_gap_analysis(pdf_text, topic, log_callback=log_callback)

    if log_callback:
        log_callback("✅ Full analysis complete!")

    return {
        "pdf_text": pdf_text,
        "analysis": analysis,
        "novelty": novelty,
        "gaps": gaps,
        "topic": topic,
    }
