"""
Conversational resume builder for users who don't have a resume yet.

This is a small state machine driven by `builder_stage` in GraphState.
bot.py is responsible for persisting builder_stage/builder_answers between
Telegram messages (see bot.py's user_sessions dict) since LangGraph state
here is per-invocation, not automatically persistent across turns unless
you wire up a checkpointer (see graph.py notes).

Stages, in order:
  skills -> projects -> experience -> education -> contact -> done
"""
from state import GraphState
from llm_client import ask
import db

STAGES = ["skills", "projects", "experience", "education", "contact"]

QUESTIONS = {
    "skills": "Let's build your resume from scratch. First — what are your core "
              "technical/professional skills? (list them, comma-separated is fine)",
    "projects": "Nice. Now tell me about 2-3 projects: name, what it does, and "
                "what you built/used.",
    "experience": "Any work experience or internships? For each: role, company, "
                  "dates, and 2-3 things you did/achieved. If none, just say 'none'.",
    "education": "What's your education background? (degree, institution, year)",
    "contact": "Last thing — your name, email, phone, and location (or 'skip' for any).",
}

WRITE_SYSTEM = """You are a professional resume writer. Given raw, informally
written answers about a candidate's skills, projects, experience, education,
and contact info, produce a clean, ATS-friendly resume in plain text
(no markdown tables). Use standard sections: Contact, Summary, Skills,
Experience, Projects, Education. Write a punchy 2-line professional summary.
Turn vague statements into concrete resume bullets using strong action verbs.
Do not invent facts not implied by the input."""


def resume_builder_node(state: GraphState) -> GraphState:
    stage = state.get("builder_stage")
    answers = dict(state.get("builder_answers") or {})
    incoming_text = state.get("user_text", "").strip()

    # First entry into the flow: no stage yet, just ask the first question.
    if stage is None:
        return {
            **state,
            "builder_stage": STAGES[0],
            "builder_answers": answers,
            "reply_text": QUESTIONS[STAGES[0]],
        }

    # Record the answer to the stage we just asked about.
    answers[stage] = incoming_text
    current_index = STAGES.index(stage)

    # More questions left?
    if current_index + 1 < len(STAGES):
        next_stage = STAGES[current_index + 1]
        return {
            **state,
            "builder_stage": next_stage,
            "builder_answers": answers,
            "reply_text": QUESTIONS[next_stage],
        }

    # Done collecting — generate the resume.
    raw_answers_text = "\n\n".join(f"{k.upper()}:\n{v}" for k, v in answers.items())
    resume_text = ask(WRITE_SYSTEM, raw_answers_text, max_tokens=1500)

    resume_id = db.save_resume(
        telegram_id=state["telegram_id"],
        content=resume_text,
        kind="base",
    )

    reply = (
        "Here's your resume:\n\n"
        f"{resume_text}\n\n"
        "I saved this as your base resume — send me a job description any time "
        "and I'll tailor it + write a cover letter. Want me to score it first? Send /score."
    )

    return {
        **state,
        "builder_stage": "done",
        "builder_answers": answers,
        "resume_text": resume_text,
        "resume_id": resume_id,
        "reply_text": reply,
    }