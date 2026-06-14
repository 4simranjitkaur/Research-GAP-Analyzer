from langchain_core.tools import tool
import os
import tempfile
import requests


@tool
def read_pdf_from_url(url: str) -> str:
    """Download and extract text from a PDF file given its URL. Great for arxiv papers."""
    try:
        import fitz  # PyMuPDF

        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(response.content)
            tmp_path = f.name

        doc = fitz.open(tmp_path)
        text_parts = []

        for i, page in enumerate(doc):
            if i >= 8:
                break
            text_parts.append(f"--- Page {i+1} ---\n{page.get_text()}")

        doc.close()
        os.unlink(tmp_path)

        full_text = "\n".join(text_parts)
        return f"PDF content from {url}:\n\n{full_text[:4000]}"

    except Exception as e:
        return f"Could not read PDF from {url}: {str(e)}"


@tool
def search_arxiv(query: str) -> str:
    """Search arxiv for academic papers on a topic. Returns titles, authors, summaries and PDF links."""
    try:
        import arxiv

        search = arxiv.Search(
            query=query,
            max_results=4,
            sort_by=arxiv.SortCriterion.Relevance
        )

        results = []
        for paper in search.results():
            results.append(
                f"Title: {paper.title}\n"
                f"Authors: {', '.join(a.name for a in paper.authors[:3])}\n"
                f"Published: {paper.published.strftime('%Y-%m')}\n"
                f"Summary: {paper.summary[:400]}...\n"
                f"PDF: {paper.pdf_url}\n"
            )

        if not results:
            return f"No arxiv papers found for: {query}"

        return f"Arxiv results for '{query}':\n\n" + "\n---\n".join(results)

    except Exception as e:
        return f"Arxiv search failed: {str(e)}"
