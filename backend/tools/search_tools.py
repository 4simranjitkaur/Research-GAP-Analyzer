import os
import tempfile
import requests
from bs4 import BeautifulSoup
from langchain.tools import tool
from tavily import TavilyClient


def get_tavily_client() -> TavilyClient:
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY is not set. Add it to backend/.env to use web search.")
    return TavilyClient(api_key=api_key)


@tool
def web_search(query: str) -> str:
    """Search the web for information on a given query. Returns titles, URLs, and snippets."""
    try:
        results = get_tavily_client().search(query=query, max_results=5, search_depth="advanced")
        formatted = []
        for r in results.get("results", [])[:4]:
            snippet = r['content'][:300]
            formatted.append(f"Title: {r['title']}\nURL: {r['url']}\nSnippet: {snippet}\n")
        return "\n---\n".join(formatted) if formatted else "No results found."
    except Exception as e:
        return f"Search failed: {str(e)}"


@tool
def read_url(url: str) -> str:
    """Fetch and read the full text content of a webpage URL."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; ResearchBot/1.0)"}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        if len(text) > 2000:
            text = text[:2000] + "\n\n[... content truncated ...]"
        return text if text.strip() else "Could not extract readable content."
    except Exception as e:
        return f"Failed to read URL: {str(e)}"


@tool
def read_pdf(url: str) -> str:
    """Download and extract text from a PDF file given its URL."""
    try:
        import fitz
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(response.content)
                tmp_path = tmp.name
            doc = fitz.open(tmp_path)
            text = "".join(page.get_text() for page in doc[:8])
            doc.close()
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
        if len(text) > 2500:
            text = text[:2500] + "\n\n[... PDF truncated ...]"
        return text if text.strip() else "Could not extract text from PDF."
    except Exception as e:
        return f"Failed to read PDF: {str(e)}"


@tool
def search_arxiv(query: str) -> str:
    """Search ArXiv for recent research papers on a topic.
    Returns paper titles, authors, abstracts and PDF links."""
    try:
        import urllib.request
        import urllib.parse
        import xml.etree.ElementTree as ET

        encoded = urllib.parse.quote(query)
        params = "start=0&max_results=4&sortBy=submittedDate&sortOrder=descending"
        url = f"http://export.arxiv.org/api/query?search_query=all:{encoded}&{params}"

        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            xml_data = resp.read()

        root = ET.fromstring(xml_data)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entries = root.findall("atom:entry", ns)

        results = []
        for entry in entries:
            title = entry.find("atom:title", ns).text.strip().replace("\n", " ")
            abstract = entry.find("atom:summary", ns).text.strip().replace("\n", " ")[:300]
            authors = [a.find("atom:name", ns).text for a in entry.findall("atom:author", ns)][:3]
            link = entry.find("atom:id", ns).text.strip()
            pdf_link = link.replace("abs", "pdf")
            author_str = ", ".join(authors)
            results.append(
                f"Title: {title}\nAuthors: {author_str}\nAbstract: {abstract}...\nPDF: {pdf_link}\n"
            )

        return "\n---\n".join(results) if results else "No papers found."
    except Exception as e:
        return f"ArXiv search failed: {str(e)}"
