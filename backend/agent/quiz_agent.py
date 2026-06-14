"""
QuizAgent — generates MCQ quiz from a research report.
"""
import os
import re
import time
import json
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage
from dotenv import load_dotenv

load_dotenv()


def llm_call(prompt: str, system: str = "", temperature=0.3):
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


def generate_quiz(topic: str, report: str, num_questions: int = 5) -> list:
    """
    Generates MCQ questions from the report.
    Returns list of question dicts.
    """
    prompt = f"""Based on this research report about "{topic}", generate exactly {num_questions} multiple choice questions.

REPORT:
{report[:3000]}

Return ONLY a JSON array in this exact format:
[
  {{
    "question": "What is...?",
    "options": ["A) option1", "B) option2", "C) option3", "D) option4"],
    "answer": "A",
    "explanation": "Because..."
  }}
]

Rules:
- Questions must be based ONLY on the report content
- Each question must have exactly 4 options (A, B, C, D)
- Mix easy and hard questions
- Return ONLY the JSON array, nothing else"""

    response = llm_call(prompt)

    # Parse JSON
    try:
        match = re.search(r'\[.*\]', response, re.DOTALL)
        if match:
            questions = json.loads(match.group())
            return questions[:num_questions]
    except Exception as e:
        pass

    return []


def run_quiz_terminal(topic: str, questions: list):
    """Run interactive quiz in terminal."""
    if not questions:
        print("No questions generated.")
        return

    print("\n" + "=" * 60)
    print(f"QUIZ: {topic}")
    print(f"{len(questions)} Questions — Type A, B, C, or D to answer")
    print("=" * 60 + "\n")

    score = 0
    for i, q in enumerate(questions, 1):
        print(f"Q{i}: {q['question']}")
        for opt in q.get("options", []):
            print(f"  {opt}")

        answer = input("\nYour answer: ").strip().upper()
        correct = q.get("answer", "").upper()

        if answer == correct:
            print(f"✅ Correct! {q.get('explanation', '')}\n")
            score += 1
        else:
            print(f"❌ Wrong! Correct answer: {correct}. {q.get('explanation', '')}\n")

    print("=" * 60)
    print(f"Final Score: {score}/{len(questions)} ({int(score/len(questions)*100)}%)")
    print("=" * 60)
    return score
