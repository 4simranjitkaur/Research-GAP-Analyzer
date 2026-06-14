# ui/main.py

from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pathlib import Path
import os
import sys
import re
import uvicorn

# Path fix
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))
FRONTEND_DIR = BASE_DIR.parent / "frontend"
REPORTS_DIR = BASE_DIR / "reports"

# Agents
from agent.research_agent import run_research_with_reflection, run_research
from agent.qa_agent import ask_question
from agent.comparison_agent import run_comparison
from agent.output_agent import generate_research_paper, generate_executive_summary, generate_presentation
from agent.paper_analyzer_agent import (
    extract_text_from_pdf_bytes,
    analyze_paper,
    compute_novelty_score,
    compute_gap_analysis,
)
from output.docx_exporter import export_to_docx
from output.pptx_exporter import export_to_pptx
from output.pdf_exporter import export_to_pdf

app = FastAPI(title="Research Platform")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static
STATIC_DIR = FRONTEND_DIR / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
else:
    print(f"Warning: static directory not found: {STATIC_DIR}")


# ─────────────────────────────────────────────
# REQUEST MODELS
# ─────────────────────────────────────────────

class ResearchRequest(BaseModel):
    topic: str
    reflection: bool = True

class QARequest(BaseModel):
    question: str
    report: str
    topic: str = ""

class CompareRequest(BaseModel):
    topic1: str
    topic2: str

class ExportRequest(BaseModel):
    topic: str
    report: str
    format: str
    sources: list = []


# ─────────────────────────────────────────────
# FRONTEND
# ─────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def home():
    index_path = FRONTEND_DIR / "templates" / "index.html"
    with open(index_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


# ─────────────────────────────────────────────
# RESEARCH
# ─────────────────────────────────────────────

@app.post("/api/research")
async def api_research(data: ResearchRequest):
    try:
        if data.reflection:
            result = run_research_with_reflection(data.topic)
        else:
            result = run_research(data.topic)

        return {
            "success": True,
            "report": result.get("report", ""),
            "sources": result.get("sources", []),
            "quality_score": result.get("quality_score", None),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─────────────────────────────────────────────
# Q/A
# ─────────────────────────────────────────────

@app.post("/api/qa")
async def api_qa(data: QARequest):
    try:
        answer = ask_question(data.report, data.topic or "Research", data.question)
        return {"success": True, "answer": answer}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─────────────────────────────────────────────
# COMPARE
# ─────────────────────────────────────────────

@app.post("/api/compare")
async def api_compare(data: CompareRequest):
    try:
        result = run_comparison(data.topic1, data.topic2)
        return {
            "success": True,
            "comparison": result.get("comparison_report", "")
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─────────────────────────────────────────────
# REPORTS
# ─────────────────────────────────────────────

@app.get("/api/reports")
async def get_reports():
    reports = []
    if REPORTS_DIR.exists():
        for f in sorted(os.listdir(REPORTS_DIR), reverse=True)[:10]:
            if f.endswith(".txt"):
                reports.append({"name": f.replace(".txt", ""), "file": f})
    return reports


@app.get("/reports/{filename}")
async def download_report(filename: str):
    file_path = REPORTS_DIR / filename
    if not file_path.exists():
        return {"error": "File not found"}
    return FileResponse(file_path, media_type="text/plain")


# ─────────────────────────────────────────────
# EXPORT / DOWNLOAD
# ─────────────────────────────────────────────

@app.post("/api/export")
async def api_export(data: ExportRequest):
    try:
        safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', data.topic[:25])
        fmt = data.format

        if fmt == "report":
            file_bytes = export_to_docx(data.topic, data.report, "Research Report")
            return Response(
                content=file_bytes,
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                headers={"Content-Disposition": f'attachment; filename="report_{safe_name}.docx"'}
            )

        elif fmt == "paper":
            content = generate_research_paper(data.topic, data.report)
            file_bytes = export_to_pdf(data.topic, content, data.sources)
            return Response(
                content=file_bytes,
                media_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="paper_{safe_name}.pdf"'}
            )

        elif fmt == "presentation":
            content = generate_presentation(data.topic, data.report)
            file_bytes = export_to_pptx(data.topic, content)
            return Response(
                content=file_bytes,
                media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                headers={"Content-Disposition": f'attachment; filename="presentation_{safe_name}.pptx"'}
            )

        elif fmt == "summary":
            content = generate_executive_summary(data.topic, data.report)
            return Response(
                content=content.encode("utf-8"),
                media_type="text/plain",
                headers={"Content-Disposition": f'attachment; filename="summary_{safe_name}.txt"'}
            )

        else:
            return {"success": False, "error": f"Unknown format: {fmt}"}

    except Exception as e:
        return {"success": False, "error": str(e)}


# ─────────────────────────────────────────────
# PAPER ANALYZER — SINGLE PAPER
# ─────────────────────────────────────────────

@app.post("/api/analyze-paper")
async def api_analyze_paper(
    file: UploadFile = File(...),
    topic_hint: str = Form(default="")
):
    """
    Upload a PDF research paper. Returns:
    - analysis  (title, authors, domain, summary, contributions, limitations)
    - novelty   (score 0-10 with breakdown, compared against live ArXiv)
    - gaps      (gap score 0-10, list of gaps with severity, future directions)
    """
    try:
        pdf_bytes = await file.read()

        if not pdf_bytes or len(pdf_bytes) < 500:
            return {"success": False, "error": "Uploaded file appears to be empty or too small."}

        # Extract text
        pdf_text = extract_text_from_pdf_bytes(pdf_bytes)
        if not pdf_text or len(pdf_text.strip()) < 200:
            return {"success": False, "error": "Could not extract readable text from this PDF."}

        # Analyze paper
        analysis = analyze_paper(pdf_text)

        # Derive topic for ArXiv search
        topic = topic_hint.strip()
        if not topic:
            topic = analysis.get("domain", "machine learning")
            kws = analysis.get("keywords", [])
            if kws:
                topic = f"{topic} {' '.join(kws[:3])}"

        # Novelty score (vs live ArXiv)
        novelty = compute_novelty_score(pdf_text, topic)

        # Gap analysis
        gaps = compute_gap_analysis(pdf_text, topic)

        return {
            "success": True,
            "filename": file.filename,
            "topic": topic,
            "analysis": analysis,
            "novelty": novelty,
            "gaps": gaps,
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


# ─────────────────────────────────────────────
# PAPER ANALYZER — COMPARE TWO PAPERS
# ─────────────────────────────────────────────

@app.post("/api/compare-papers")
async def api_compare_papers(
    file1: UploadFile = File(...),
    file2: UploadFile = File(...),
    topic_hint: str = Form(default="")
):
    """
    Upload two PDFs. Returns independent analysis + novelty + gap results
    for both papers so the frontend can display a side-by-side comparison.
    """
    try:
        bytes1 = await file1.read()
        bytes2 = await file2.read()

        def _analyze_one(pdf_bytes, filename, hint):
            text = extract_text_from_pdf_bytes(pdf_bytes)
            if not text or len(text.strip()) < 200:
                return {"success": False, "error": f"Could not extract text from {filename}"}

            analysis = analyze_paper(text)

            topic = hint.strip()
            if not topic:
                topic = analysis.get("domain", "machine learning")
                kws = analysis.get("keywords", [])
                if kws:
                    topic = f"{topic} {' '.join(kws[:3])}"

            novelty = compute_novelty_score(text, topic)
            gaps = compute_gap_analysis(text, topic)

            return {
                "success": True,
                "filename": filename,
                "topic": topic,
                "analysis": analysis,
                "novelty": novelty,
                "gaps": gaps,
            }

        result1 = _analyze_one(bytes1, file1.filename, topic_hint)
        result2 = _analyze_one(bytes2, file2.filename, topic_hint)

        return {
            "success": True,
            "paper1": result1,
            "paper2": result2,
        }

    except Exception as e:
        return {"success": False, "error": str(e)}


# ─────────────────────────────────────────────
# RUN
# ─────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
