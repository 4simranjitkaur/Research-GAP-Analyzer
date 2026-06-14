"""
CriticAgent — reviews a research report and improves it.
If score < 7, rewrites with specific improvements.
"""
import os
import time
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from dotenv import load_dotenv

load_dotenv()


def llm_call(prompt: str, system: str = "", temperature=0.1):
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


def critique_report(topic: str, report: str) -> dict:
    """
    Reviews the report and returns:
    - score (0-10)
    - strengths
    - weaknesses
    - suggestions
    """
    prompt = f"""You are a strict research report reviewer. Review this report about "{topic}".

REPORT:
{report[:3000]}

Evaluate on these criteria:
1. Completeness — does it cover all key aspects?
2. Specificity — does it have concrete facts, numbers, examples?
3. Structure — is it well organized?
4. Depth — is it detailed enough?
5. Relevance — is everything on topic?

Respond in EXACTLY this format:
SCORE: [number 1-10]
STRENGTHS: [2-3 things done well]
WEAKNESSES: [2-3 specific gaps or problems]
SUGGESTIONS: [2-3 specific improvements to make]"""

    response = llm_call(prompt, system="You are a strict but fair research report critic.")

    # Parse response
    score = 7  # default
    strengths = ""
    weaknesses = ""
    suggestions = ""

    for line in response.split("\n"):
        line = line.strip()
        if line.startswith("SCORE:"):
            try:
                score = int("".join(filter(str.isdigit, line.split(":", 1)[1][:3])))
            except:
                score = 7
        elif line.startswith("STRENGTHS:"):
            strengths = line.split(":", 1)[1].strip()
        elif line.startswith("WEAKNESSES:"):
            weaknesses = line.split(":", 1)[1].strip()
        elif line.startswith("SUGGESTIONS:"):
            suggestions = line.split(":", 1)[1].strip()

    return {
        "score": score,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "suggestions": suggestions,
        "raw": response
    }


def improve_report(topic: str, report: str, critique: dict) -> str:
    """Rewrites the report based on critique feedback."""

    prompt = f"""You are a professional research writer. Improve this report about "{topic}" based on the feedback below.

ORIGINAL REPORT:
{report[:3000]}

CRITIC FEEDBACK:
- Weaknesses: {critique['weaknesses']}
- Suggestions: {critique['suggestions']}

Write an IMPROVED version of the report that:
1. Fixes all the weaknesses mentioned
2. Implements all the suggestions
3. Keeps all the good parts
4. Maintains the same structure:
   ## Executive Summary
   ## Key Findings
   ## Current Trends & Developments
   ## Challenges & Limitations
   ## Future Outlook
   ## Conclusion

Write the full improved report now:"""

    return llm_call(prompt, temperature=0.2)


def reflect_and_improve(topic: str, report: str, log_callback=None, max_rounds=2) -> dict:
    """
    Main self-reflection loop:
    1. Critique the report
    2. If score < 7, improve it
    3. Repeat up to max_rounds times
    Returns final report + critique history
    """
    history = []
    current_report = report

    for round_num in range(1, max_rounds + 1):
        if log_callback:
            log_callback(f"CriticAgent: Reviewing report (Round {round_num})...")

        critique = critique_report(topic, current_report)
        history.append(critique)

        if log_callback:
            log_callback(f"CriticAgent: Score {critique['score']}/10 — {critique['weaknesses'][:80]}...")

        if critique["score"] >= 7:
            if log_callback:
                log_callback(f"CriticAgent: Score {critique['score']}/10 — report approved!")
            break

        if log_callback:
            log_callback(f"WriterAgent: Improving report based on feedback...")

        current_report = improve_report(topic, current_report, critique)

        if log_callback:
            log_callback(f"WriterAgent: Report improved (Round {round_num} complete)")

    final_score = history[-1]["score"] if history else 0

    return {
        "report": current_report,
        "final_score": final_score,
        "rounds": len(history),
        "critique_history": history
    }
