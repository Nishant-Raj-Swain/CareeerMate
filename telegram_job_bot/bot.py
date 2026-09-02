"""
Telegram bot handlers. Each handler builds a GraphState, invokes the
compiled LangGraph, and sends back `reply_text`.

Per-user session dict (`user_sessions`) holds lightweight cross-message
state that isn't worth a DB round-trip: mainly the resume-builder's
current stage/answers. In-memory only — fine for one bot process; move
to Redis if you scale to multiple workers.
"""
import logging
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters,
)

from config import TELEGRAM_BOT_TOKEN
from graph import build_graph
from resume_parsing import extract_text
import db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

compiled_graph = build_graph()

# telegram_id -> {"builder_stage": ..., "builder_answers": {...}}
user_sessions: dict[int, dict] = {}


def _session(telegram_id: int) -> dict:
    return user_sessions.setdefault(telegram_id, {})


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.upsert_user(user.id, user.username)
    await update.message.reply_text(
        "Hey! I'm your career assistant. I can build you a learning roadmap, "
        "score/tailor your resume, write cover letters, and track applications.\n\n"
        "Send /roadmap <topic>, upload a resume, or send /build to create one from scratch."
    )


async def roadmap_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    domain = " ".join(context.args)
    if not domain:
        await update.message.reply_text("Usage: /roadmap <domain or interest>, e.g. /roadmap data engineering")
        return
    result = compiled_graph.invoke({
        "telegram_id": update.effective_user.id,
        "user_text": domain,
        "intent": "roadmap",
    })
    await update.message.reply_text(result["reply_text"], parse_mode="Markdown")


async def build_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    session = _session(telegram_id)
    session["builder_stage"] = None
    session["builder_answers"] = {}

    result = compiled_graph.invoke({
        "telegram_id": telegram_id,
        "user_text": "",
        "intent": "resume_build",
        "builder_stage": None,
        "builder_answers": {},
    })
    session["builder_stage"] = result.get("builder_stage")
    session["builder_answers"] = result.get("builder_answers", {})
    await update.message.reply_text(result["reply_text"])


async def jobsearch_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text("Usage: /jobsearch <role/keywords>, e.g. /jobsearch python backend Bengaluru")
        return
    result = compiled_graph.invoke({
        "telegram_id": update.effective_user.id,
        "user_text": query,
        "job_query": query,
        "intent": "job_search",
    })
    await update.message.reply_text(result["reply_text"], parse_mode="Markdown", disable_web_page_preview=True)


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = compiled_graph.invoke({
        "telegram_id": update.effective_user.id,
        "user_text": "",
        "intent": "status",
    })
    await update.message.reply_text(result["reply_text"], parse_mode="Markdown")


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """A resume file upload -> extract text -> score node."""
    telegram_id = update.effective_user.id
    doc = update.message.document
    file = await context.bot.get_file(doc.file_id)
    file_bytes = await file.download_as_bytearray()

    try:
        resume_text = extract_text(bytes(file_bytes), doc.file_name)
    except ValueError as e:
        await update.message.reply_text(str(e))
        return

    await update.message.reply_text("Got it — scoring your resume...")
    result = compiled_graph.invoke({
        "telegram_id": telegram_id,
        "user_text": "",
        "resume_text": resume_text,
        "intent": "resume_upload",
    })
    await update.message.reply_text(result["reply_text"], parse_mode="Markdown")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Free text with no command. Three cases, checked in order:
      1. User is mid-way through the guided resume builder -> continue it.
      2. Message looks long (likely a pasted job description) -> tailor.
      3. Otherwise -> let the router classify (roadmap text, greetings, etc).
    """
    telegram_id = update.effective_user.id
    session = _session(telegram_id)
    text = update.message.text.strip()

    if session.get("builder_stage") and session["builder_stage"] != "done":
        result = compiled_graph.invoke({
            "telegram_id": telegram_id,
            "user_text": text,
            "intent": "resume_build",
            "builder_stage": session["builder_stage"],
            "builder_answers": session.get("builder_answers", {}),
        })
        session["builder_stage"] = result.get("builder_stage")
        session["builder_answers"] = result.get("builder_answers", {})
        await update.message.reply_text(result["reply_text"], parse_mode="Markdown")
        return

    # Heuristic: a long paste is almost certainly a job description, not chit-chat.
    if len(text) > 300:
        result = compiled_graph.invoke({
            "telegram_id": telegram_id,
            "user_text": text,
            "job_description": text,
            "intent": "tailor",
        })
        await update.message.reply_text(result["reply_text"], parse_mode="Markdown")
        return

    result = compiled_graph.invoke({
        "telegram_id": telegram_id,
        "user_text": text,
        # intent left unset on purpose -> router_node classifies it
    })
    await update.message.reply_text(result["reply_text"], parse_mode="Markdown")


def main():
    db.init_db()
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("roadmap", roadmap_cmd))
    app.add_handler(CommandHandler("build", build_cmd))
    app.add_handler(CommandHandler("jobsearch", jobsearch_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Bot starting (polling)...")
    app.run_polling()


if __name__ == "__main__":
    main()