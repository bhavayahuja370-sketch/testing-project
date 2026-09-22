# Nova — AI Student Assistant

Flask chatbot with OpenAI responses and Supabase PostgreSQL chat history.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

In `.env`, set `OPENAI_API_KEY` and paste the Supabase **Session pooler** connection string into `DATABASE_URL`. Keep `sslmode=require` in the URL.

```powershell
python app.py
```

Open `http://127.0.0.1:5000`.

## Chat history

The application creates a `chat_messages` table in Supabase. Each row has `id`, `session_id`, `role`, `content`, and `created_at`.

- `POST /api/chat` saves the user's message, sends the last 20 messages to OpenAI as context, and saves the assistant response.
- `GET /api/history` returns the active browser session's messages in chronological order.

If Supabase or OpenAI is unavailable, the UI still works and returns a safe fallback response. API keys and database URLs stay server-side; do not add them to browser JavaScript or commit `.env`.
