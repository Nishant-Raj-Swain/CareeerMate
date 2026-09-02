"""
Takes the user's base resume + a job description, produces a tailored
resume and a cover letter, and saves both plus a draft application row.
"""
from state import GraphState
from llm_client import ask
import db

TAILOR_SYSTEM = """You rewrite resumes to match a specific job description
without fabricating experience. Reorder and rephrase existing bullets to
foreground relevant skills, mirror the job description's terminology where
truthful, and tighten the summary. Keep it plain text, ATS-friendly, same
overall length as the input. Output ONLY the tailored resume text."""

COVER_LETTER_SYSTEM = """Write a concise, specific cover letter (250-350 words)
based on the candidate's resume and the target job description. No generic
filler ("I am writing to express my interest..."). Open with something
concrete and relevant. Plain text, ready to send."""


def tailor_node(state: GraphState) -> GraphState:
    base_row = db.get_latest_base_resume(state["telegram_id"])
    if base_row is None:
        return {**state, "reply_text": "I don't have a base resume for you yet — "
                                        "upload one or send /build to create one first."}

    job_description = state.get("job_description") or state.get("user_text", "")
    if not job_description.strip():
        return {**state, "reply_text": "Send me the job description text and I'll tailor your resume to it."}

    base_resume = base_row["content"]

    tailored_resume = ask(
        TAILOR_SYSTEM,
        f"BASE RESUME:\n{base_resume}\n\nJOB DESCRIPTION:\n{job_description}",
        max_tokens=1500,
    )
    cover_letter = ask(
        COVER_LETTER_SYSTEM,
        f"RESUME:\n{tailored_resume}\n\nJOB DESCRIPTION:\n{job_description}",
        max_tokens=800,
    )

    tailored_id = db.save_resume(
        telegram_id=state["telegram_id"],
        content=tailored_resume,
        kind="tailored",
        job_description=job_description,
    )

    # Create a draft application row so it shows up in /status right away.
    db.create_application(
        telegram_id=state["telegram_id"],
        job_title="(untitled — from pasted description)",
        company=None,
        job_url=None,
        resume_id=tailored_id,
        cover_letter=cover_letter,
        status="draft",
    )

    reply = (
        "*Tailored resume:*\n\n" + tailored_resume +
        "\n\n*Cover letter:*\n\n" + cover_letter +
        "\n\nSaved as a draft application — send /status to see all your tracked applications."
    )
    return {**state, "tailored_resume": tailored_resume, "cover_letter": cover_letter, "reply_text": reply}