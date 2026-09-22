import os
import re
from datetime import datetime
from uuid import uuid4

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, session

import db

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY", "nova-local-development-key")


def demo_response(message: str) -> str:
    """Offline fallback used only when the selected provider is unavailable."""
    lower = message.lower()
    if "python" in lower:
        return "Python is a readable, general-purpose programming language used for web apps, automation, data, and AI."
    if "dbms" in lower or "database" in lower:
        return "A DBMS stores, organizes, retrieves, and protects data. PostgreSQL and Supabase are common examples."
    return "I could not reach the AI service right now. Please try again in a moment."


def session_id() -> str:
    """Return the server-owned ID for this browser conversation."""
    if "chat_session_id" not in session:
        session["chat_session_id"] = uuid4().hex
    return session["chat_session_id"]


def openai_response(history: list[dict], subject: str, level: str) -> str | None:
    """Generate a response from the complete recent role-based conversation."""
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        from openai import OpenAI

        messages = [{
            "role": "system",
            "content": (
                "You are Nova, a clear and encouraging student assistant. "
                f"Adapt answers for a {level} learner studying {subject}. "
                "Use the prior conversation only as context, and do not complete graded work."
            ),
        }]
        messages.extend(
            {"role": item["role"], "content": item["content"]}
            for item in history
            if item.get("role") in {"user", "assistant"} and item.get("content")
        )
        completion = OpenAI(api_key=api_key).chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            messages=messages,
        )
        return (completion.choices[0].message.content or "").strip() or None
    except Exception as error:
        app.logger.warning("OpenAI request failed: %s", type(error).__name__)
        return None


def gemini_response(history: list[dict], subject: str, level: str) -> str | None:
    """Generate a response from the same saved conversation with Gemini."""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        from google import genai

        transcript = "\n".join(
            f"{item['role'].title()}: {item['content']}"
            for item in history
            if item.get("role") in {"user", "assistant"} and item.get("content")
        )
        response = genai.Client(api_key=api_key).models.generate_content(
            model=os.environ.get("GEMINI_MODEL", "gemini-2.0-flash"),
            contents=(
                "You are Nova, a clear and encouraging student assistant. "
                f"Adapt answers for a {level} learner studying {subject}. "
                "Use this recent conversation as context and do not complete graded work.\n\n"
                f"{transcript}"
            ),
        )
        return (response.text or "").strip() or None
    except Exception as error:
        app.logger.warning("Gemini request failed: %s", type(error).__name__)
        return None


AI_PROVIDERS = {"gemini": gemini_response, "openai": openai_response}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/history", methods=["GET"])
def history():
    """Return the active browser session's messages in display order."""
    requested_limit = request.args.get("limit", 20)
    try:
        limit = max(1, min(int(requested_limit), 100))
    except (TypeError, ValueError):
        limit = 20
    active_session = session_id()
    return jsonify({"session_id": active_session, "messages": db.get_recent_messages(active_session, limit)})


@app.route("/api/health", methods=["GET"])
def health():
    """Small safe diagnostic endpoint; it never returns keys or chat content."""
    return jsonify({
        "status": "ok",
        "database": db.check_connection(),
        "providers": {
            "gemini": bool(os.environ.get("GEMINI_API_KEY", "").strip()),
            "openai": bool(os.environ.get("OPENAI_API_KEY", "").strip()),
        },
    })


@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    message = str(data.get("message", "")).strip()
    if not message:
        return jsonify({"error": "Please enter a question."}), 400

    subject = str(data.get("subject", "General"))[:80]
    level = str(data.get("level", "High school"))[:80]
    requested_model = str(data.get("model", "gemini")).strip().lower()
    model = requested_model if requested_model in AI_PROVIDERS else "gemini"
    active_session = session_id()

    # Persist first so the current prompt is part of the model context.
    db.save_message(active_session, "user", message)
    recent_history = db.get_recent_messages(active_session, limit=20)
    answer = AI_PROVIDERS[model](recent_history, subject, level) or demo_response(message)
    db.save_message(active_session, "assistant", answer)

    return jsonify({"reply": answer, "time": datetime.now().strftime("%I:%M %p"), "model": model})


@app.route("/api/flashcards", methods=["POST"])
def flashcards():
    data = request.get_json(silent=True) or {}
    topic = re.sub(r"[^\w\s-]", "", str(data.get("topic", "your topic"))).strip()[:80]
    return jsonify({"cards": [
        {"front": f"What is the main idea of {topic}?", "back": "State it in one precise sentence."},
        {"front": f"Give an example of {topic}.", "back": "Choose a clear, real or worked example."},
        {"front": f"Why does {topic} matter?", "back": "Connect it to a wider concept or real use."},
    ]})


# This is safe to fail: chat works with an offline fallback if Supabase is unavailable.
db.init_db()

if __name__ == "__main__":
    app.run(debug=True)
