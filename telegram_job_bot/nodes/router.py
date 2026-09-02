"""
Router node.

Most intents are actually set directly by bot.py from the Telegram command
(/roadmap, /status, a document upload, etc.) before the graph even runs, so
this node's real job is classifying *free-text* messages that arrive with
no command attached — e.g. someone just answers a resume-builder question,
or types "find me data analyst jobs in Bhubaneswar" with no /jobsearch.

If intent is already set (by bot.py), this node just passes state through.
"""
from state import GraphState
from llm_client import ask_json

CLASSIFY_SYSTEM = """You classify a Telegram message for a career-assistant bot.
Return JSON: {"intent": one of
  ["roadmap", "job_search", "resume_build", "status", "unknown"]}
- "roadmap": user names a domain/interest and wants a learning path.
- "job_search": user wants jobs found for a role/location.
- "resume_build": user is answering questions about skills/projects/experience,
  or explicitly says they don't have a resume.
- "status": user wants to see their tracked applications.
- "unknown": anything else (greetings, unclear text)."""


def router_node(state: GraphState) -> GraphState:
    if state.get("intent"):
        return state  # already routed by bot.py (commands, file uploads, etc.)

    text = state.get("user_text", "")
    if not text.strip():
        return {**state, "intent": "unknown"}

    try:
        result = ask_json(CLASSIFY_SYSTEM, text, max_tokens=50)
        intent = result.get("intent", "unknown")
    except Exception:
        intent = "unknown"

    return {**state, "intent": intent}