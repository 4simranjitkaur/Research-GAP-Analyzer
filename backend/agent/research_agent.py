import os
import re
import time
import json
from typing import Annotated, TypedDict
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, END

load_dotenv()

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.search_tools import web_search, read_url, read_pdf, search_arxiv


class AgentState(TypedDict):
    topic: str
    search_results: list
    read_contents: list
    sources: list
    report: str
    step_logs: list


def groq_call(messages, temperature=0):
    llm = ChatGroq(
        model="llama-3.1-8b-instant",
        temperature=temperature,
        api_key=os.getenv("GROQ_API_KEY"),
    )
    for attempt in range(3):
        try:
            return llm.invoke(messages)
        except Exception as e:
            if "429" in str(e) or "rate_limit" in str(e).lower():
                wait = 60 * (attempt + 1)
                print(f"Rate limit hit, waiting {wait}s...")
                time.sleep(wait)
            else:
                raise
    raise Exception("Failed after 3 retries")


def search_node(state: AgentState):
    topic = state["topic"]
    logs = []
    all_results = []

    queries = [
        f"{topic} latest developments 2025",
        f"{topic} challenges limitations",
        f"{topic} real world applications",
    ]

    for query in queries:
        logs.append(f"Searching: {query}")
        try:
            result = web_search.invoke({"query": query})
            all_results.append(result)
        except Exception as e:
            logs.append(f"Search failed: {str(e)}")

    return {
        "search_results": all_results,
        "step_logs": state.get("step_logs", []) + logs,
    }


def arxiv_node(state: AgentState):
    topic = state["topic"]
    logs = []

    logs.append(f"Searching ArXiv for research papers on: {topic}...")
    try:
        result = search_arxiv.invoke({"query": topic})
        logs.append("ArXiv papers found successfully")
    except Exception as e:
        result = ""
        logs.append(f"ArXiv search failed: {str(e)}")

    current_results = state.get("search_results", [])
    if result.strip() and "No papers found" not in result:
        current_results = current_results + [f"ARXIV RESEARCH PAPERS:\n{result}"]
        logs.append("Added ArXiv papers to research context")

    return {
        "search_results": current_results,
        "step_logs": state.get("step_logs", []) + logs,
    }


def pick_urls_node(state: AgentState):
    topic = state["topic"]
    all_search_text = "\n\n".join(state["search_results"])
    logs = []

    prompt = f"""From these search results about "{topic}", extract exactly 3 of the most relevant and informative URLs.

SEARCH RESULTS:
{all_search_text[:3000]}

Return ONLY a JSON array of 3 URLs like this:
["https://url1.com", "https://url2.com", "https://url3.com"]

Return nothing else — just the JSON array."""

    logs.append("Picking best URLs to read...")
    response = groq_call([HumanMessage(content=prompt)])

    urls = []
    try:
        match = re.search(r'\[.*?\]', response.content, re.DOTALL)
        if match:
            urls = json.loads(match.group())
            urls = [u for u in urls if u.startswith("http")][:3]
    except Exception:
        urls = re.findall(r'https?://[^\s\n"\'<>]+', response.content)[:3]

    logs.append(f"Selected {len(urls)} URLs to read")
    return {
        "sources": urls,
        "step_logs": state.get("step_logs", []) + logs,
    }


def read_node(state: AgentState):
    logs = []
    contents = []

    for url in state["sources"]:
        logs.append(f"Reading: {url[:70]}...")
        try:
            if url.endswith(".pdf"):
                content = read_pdf.invoke({"url": url})
            else:
                content = read_url.invoke({"url": url})

            if content and len(content.strip()) > 100:
                contents.append(f"SOURCE: {url}\n\n{content[:2000]}")
            else:
                logs.append(f"Skipped (no content): {url[:60]}")
        except Exception as e:
            logs.append(f"Failed to read: {url[:60]}")

    return {
        "read_contents": contents,
        "step_logs": state.get("step_logs", []) + logs,
    }


def report_node(state: AgentState):
    topic = state["topic"]
    logs = []

    all_context = []
    all_context.extend(state.get("search_results", []))
    all_context.extend(state.get("read_contents", []))
    context = "\n\n---\n\n".join(all_context)[:6000]

    logs.append("Compiling final report...")

    prompt = f"""You are a professional research analyst. Based ONLY on the research data below about "{topic}", write a detailed, well-structured report.

RESEARCH DATA:
{context}

Write the report using EXACTLY this structure:

## Executive Summary
(2-3 sentence overview of the topic and key findings)

## Key Findings
- (finding 1)
- (finding 2)
- (finding 3)
- (finding 4)
- (finding 5)

## Current Trends & Developments
(Detailed paragraphs on what is happening right now)

## Challenges & Limitations
(Real challenges found in the research)

## Future Outlook
(Where is this field heading)

## Conclusion
(Key takeaways in 2-3 sentences)

Rules:
- Only use facts from the research data provided
- Be specific with numbers, names, examples where available
- Do not pad with generic statements
- Minimum 600 words"""

    response = groq_call([HumanMessage(content=prompt)], temperature=0.2)
    logs.append("Report compiled successfully.")

    return {
        "report": response.content,
        "step_logs": state.get("step_logs", []) + logs,
    }


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("search", search_node)
    graph.add_node("arxiv", arxiv_node)
    graph.add_node("pick_urls", pick_urls_node)
    graph.add_node("read", read_node)
    graph.add_node("report", report_node)

    graph.set_entry_point("search")
    graph.add_edge("search", "arxiv")
    graph.add_edge("arxiv", "pick_urls")
    graph.add_edge("pick_urls", "read")
    graph.add_edge("read", "report")
    graph.add_edge("report", END)

    return graph.compile()


def save_report(topic: str, report: str, sources: list):
    from datetime import datetime
    reports_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports"
    )
    os.makedirs(reports_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_topic = re.sub(r'[^a-zA-Z0-9_]', '_', topic[:30])
    filename = f"{timestamp}_{safe_topic}.txt"
    filepath = os.path.join(reports_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"Topic: {topic}\n")
        f.write(f"Generated: {datetime.now().strftime('%B %d, %Y %H:%M')}\n")
        f.write(f"Sources: {len(sources)}\n")
        f.write("=" * 60 + "\n\n")
        f.write(report)
        f.write("\n\n" + "=" * 60 + "\nSOURCES:\n")
        for i, url in enumerate(sources, 1):
            f.write(f"{i}. {url}\n")

    return filepath


def run_research(topic: str, log_callback=None):
    graph = build_graph()

    initial_state: AgentState = {
        "topic": topic,
        "search_results": [],
        "read_contents": [],
        "sources": [],
        "report": "",
        "step_logs": [f"Starting research on: {topic}"],
    }

    final_state = {
        "report": "",
        "sources": [],
        "step_logs": [],
    }

    seen_logs = set()

    for state_chunk in graph.stream(initial_state):
        for node_name, node_state in state_chunk.items():
            if log_callback and "step_logs" in node_state:
                for log in node_state["step_logs"]:
                    if log not in seen_logs:
                        seen_logs.add(log)
                        log_callback(log)
            if node_state.get("report", "").strip():
                final_state["report"] = node_state["report"]
            if node_state.get("sources"):
                final_state["sources"] = node_state["sources"]
            if node_state.get("step_logs"):
                final_state["step_logs"] = node_state["step_logs"]

    if final_state["report"].strip():
        saved_path = save_report(topic, final_state["report"], final_state["sources"])
        if log_callback:
            log_callback(f"Report saved: {saved_path}")
        final_state["saved_path"] = saved_path

    return final_state


def run_research_with_reflection(topic: str, log_callback=None) -> dict:
    """
    Full pipeline: research + self-reflection loop.
    Generates report then critiques and improves it.
    """
    # Step 1: Run base research
    result = run_research(topic, log_callback=log_callback)

    report = result.get("report", "")
    if not report.strip():
        return result

    # Step 2: Self-reflection loop
    from agent.critic_agent import reflect_and_improve

    if log_callback:
        log_callback("Starting self-reflection loop...")

    reflection = reflect_and_improve(
        topic=topic,
        report=report,
        log_callback=log_callback,
        max_rounds=2
    )

    # Step 3: Update result with improved report
    result["report"] = reflection["report"]
    result["quality_score"] = reflection["final_score"]
    result["reflection_rounds"] = reflection["rounds"]
    result["critique"] = reflection["critique_history"][-1] if reflection["critique_history"] else {}

    # Re-save improved report
    if result["report"].strip():
        saved_path = save_report(topic, result["report"], result.get("sources", []))
        if log_callback:
            log_callback(f"Improved report saved: {saved_path}")
        result["saved_path"] = saved_path

    return result
