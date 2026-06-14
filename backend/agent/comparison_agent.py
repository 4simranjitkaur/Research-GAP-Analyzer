"""
ComparisonAgent — researches 2 topics and generates a side-by-side comparison report.
"""
import os
import time
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from dotenv import load_dotenv

load_dotenv()

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def llm_call(prompt: str, system: str = "", temperature=0.2):
    llm = ChatGroq(
        model="llama-3.1-8b-instant",
        temperature=temperature,
        api_key=os.getenv("GROQ_API_KEY"),
    )
    messages = []
    if system:
        messages.append(SystemMessage(content=system))
    messages.append(HumanMessage(content=prompt))
    for attempt in range(3):
        try:
            return llm.invoke(messages).content
        except Exception as e:
            if "429" in str(e) or "rate_limit" in str(e).lower():
                wait = 60 * (attempt + 1)
                print(f"Rate limit, waiting {wait}s...")
                time.sleep(wait)
            else:
                raise
    raise Exception("LLM failed after 3 retries")


def run_comparison(topic1: str, topic2: str, log_callback=None) -> dict:
    """
    Researches both topics then generates a comparison report.
    """
    from agent.research_agent import run_research

    # Research topic 1
    if log_callback:
        log_callback(f"Researching Topic 1: {topic1}...")
    result1 = run_research(topic1, log_callback=log_callback)

    # Research topic 2
    if log_callback:
        log_callback(f"Researching Topic 2: {topic2}...")
    result2 = run_research(topic2, log_callback=log_callback)

    report1 = result1.get("report", "")
    report2 = result2.get("report", "")

    if log_callback:
        log_callback("ComparisonAgent: Generating comparison report...")

    prompt = f"""You are a research analyst. Compare "{topic1}" vs "{topic2}" based on the research below.

REPORT ON {topic1.upper()}:
{report1[:2000]}

REPORT ON {topic2.upper()}:
{report2[:2000]}

Write a detailed comparison report using EXACTLY this structure:

## Overview
(Brief intro to both topics)

## Side-by-Side Comparison

| Aspect | {topic1} | {topic2} |
|--------|----------|----------|
| Maturity | ... | ... |
| Use Cases | ... | ... |
| Strengths | ... | ... |
| Limitations | ... | ... |
| Future Potential | ... | ... |

## Key Similarities
(What do they have in common?)

## Key Differences
(How are they fundamentally different?)

## When to Use {topic1}
(Specific scenarios)

## When to Use {topic2}
(Specific scenarios)

## Verdict
(Which is better and in what context? Be specific.)

Be specific and use facts from the research data provided."""

    comparison_report = llm_call(prompt)

    if log_callback:
        log_callback("Comparison report compiled successfully!")

    # Save comparison report
    import re
    from datetime import datetime
    reports_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports"
    )
    os.makedirs(reports_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', f"{topic1}_vs_{topic2}"[:40])
    filepath = os.path.join(reports_dir, f"{timestamp}_COMPARISON_{safe_name}.txt")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"COMPARISON: {topic1} vs {topic2}\n")
        f.write(f"Generated: {datetime.now().strftime('%B %d, %Y %H:%M')}\n")
        f.write("=" * 60 + "\n\n")
        f.write(comparison_report)

    if log_callback:
        log_callback(f"Comparison saved: {filepath}")

    return {
        "topic1": topic1,
        "topic2": topic2,
        "report1": report1,
        "report2": report2,
        "comparison_report": comparison_report,
        "sources": result1.get("sources", []) + result2.get("sources", []),
        "saved_path": filepath
    }
