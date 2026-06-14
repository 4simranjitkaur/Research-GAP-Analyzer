import os
import time
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from dotenv import load_dotenv

load_dotenv()


def groq_call(messages, temperature=0.3):
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


def ask_question(report: str, topic: str, question: str) -> str:
    """Ask a follow-up question about a research report."""

    system = f"""You are a research assistant. You have access to a research report about "{topic}".
Answer questions about this report accurately and concisely.
Only use information from the report — do not make up facts.
If the answer is not in the report, say so clearly."""

    prompt = f"""RESEARCH REPORT:
{report}

QUESTION: {question}

Answer the question based only on the report above."""

    response = groq_call([
        SystemMessage(content=system),
        HumanMessage(content=prompt)
    ])
    return response.content


def qa_session(report: str, topic: str):
    """Run an interactive Q&A session in the terminal about a report."""
    print("\n" + "=" * 60)
    print(f"Q&A Session: {topic}")
    print("Ask any question about the report. Type 'exit' to quit.")
    print("=" * 60 + "\n")

    while True:
        question = input("Your question: ").strip()
        if not question:
            continue
        if question.lower() in ["exit", "quit", "q"]:
            print("Ending Q&A session.")
            break

        print("\nThinking...\n")
        answer = ask_question(report, topic, question)
        print(f"Answer: {answer}\n")
        print("-" * 40)