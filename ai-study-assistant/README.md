# AI Study Assistant

An adaptive AI tutor that runs in the browser. Sign in with Google, type any topic, and it
explains it, gives examples, quizzes you and grades your answers. If you struggle it re-teaches
the topic more simply; if you pass it suggests what to learn next.

Built with **Python**, **LangGraph**, **Groq**, **Streamlit** and **PostgreSQL** (Neon).

## Features

- **Learning loop:** explanation → examples → quiz → grade → re-explain or move on.
- **Mastery tracking:** a score per concept, updated by every quiz, review and coding attempt.
- **Spaced repetition:** weak concepts come back for review sooner.
- **Document tutor:** upload a PDF, DOCX, TXT or Markdown file and ask questions about it.
- **Study planner:** a week-by-week plan built from your mastery scores.
- **Coding practice:** generated problems, run and graded in a sandbox, with hints.
- **Accounts and history:** Google sign-in, per-user data, and past sessions you can reopen.

## How it works

```
Topic → Understand → Explain → Examples → Quiz → (wait for answers) → Grade → Update mastery
                                            ↑                                      │
                                            └──── score < 70%: re-explain ─────────┤
                                                                                   └─ passed → Next topic
```

The app is a single Streamlit process: the Streamlit UI (frontend) and the LangGraph workflow
and database code (backend) run together, so one command starts everything.

## Setup

**Requirements:** Python 3.11+, a [Groq API key](https://console.groq.com/keys), a
[Google OAuth client](https://console.cloud.google.com/apis/credentials) and, for hosting,
a free [Neon](https://neon.tech) Postgres database.

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env          # macOS/Linux: cp .env.example .env
```

Then fill in `.env`:

| Variable | What it is |
|:--|:--|
| `GROQ_API_KEY_1` … `GROQ_API_KEY_8` | Groq API keys (the same key can be used for all eight) |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Google OAuth client credentials |
| `GOOGLE_REDIRECT_URI` | `http://localhost:8501` locally; your public URL when hosted |
| `DATABASE_URL` | Neon Postgres connection string. Leave empty to use local SQLite files |

Keep real values only in `.env`, which git ignores. `.env.example` must hold placeholders only.

## Run

```bash
streamlit run app.py
```

Open http://localhost:8501 and sign in with Google.

## Database

With `DATABASE_URL` set, everything (accounts, history, mastery, plans, documents, sign-ins and
paused quizzes) is stored in Postgres and survives restarts and redeploys. The tables are created
automatically on first start. Without it, the app uses local SQLite files, which is fine for
development but is wiped on hosts with temporary disks (Render, Railway, Hugging Face Spaces).

To get a Neon connection string from the command line:

```bash
npm install -g neonctl
neonctl auth
neonctl projects create --name ai-study-assistant --region-id aws-ap-southeast-1 --set-context
neonctl connection-string --pooled
```

## Deploy

1. Push the code to your host (Render, Railway, Hugging Face Spaces, …).
2. Set the same variables as in `.env` in the host's environment settings, with
   `GOOGLE_REDIRECT_URI` set to your public URL.
3. Add that URL as an **Authorized redirect URI** on the Google OAuth client.
4. Start command: `streamlit run app.py --server.port $PORT --server.address 0.0.0.0`

## Tests

```bash
pytest -q
```

Postgres tests run only when `TEST_DATABASE_URL` points at a **throwaway** database, because they
drop every table afterwards.

## Project structure

```
app.py        Streamlit entry point
auth/         Google sign-in and sessions
db/           Database connection, schema and repositories
graph/        LangGraph workflow (nodes, edges, state)
learning/     Mastery, spaced repetition and study planner logic
rag/          Document upload and search
coding/       Coding problems, sandboxed runner and grading
llm/          Groq model setup
prompts/      Prompt templates
ui/           Streamlit components and styles
tests/        pytest suite
```
