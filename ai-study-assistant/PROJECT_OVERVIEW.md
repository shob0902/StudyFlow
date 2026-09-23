# AI Study Assistant — Project Overview

## What it is

An adaptive, AI-powered tutor in the browser. You sign in with Google, type a topic ("What is an embedding?"),
and the app explains it, shows examples, quizzes you, grades your answers, and then
**decides what happens next**: re-teach the topic more simply if you struggled, or
recommend the next topic if you passed.

It is built as a **stateful agentic workflow** — not a chatbot and not a linear script.
The flow branches, pauses for the human, and loops.

| | |
|---|---|
| **Stack** | Python 3.11+, LangChain 1.x, LangGraph 1.x (SqliteSaver), Groq (`openai/gpt-oss-120b`), Streamlit, Pydantic, Google OAuth 2.0, SQLite |
| **Entry point** | `streamlit run app.py` |
| **Secondary goal** | A readable reference for learning LangChain/LangGraph — every module is small and commented (see `LEARNING_GUIDE.md`) |

---

## What it does — the learning loop

0. **Sign in with Google** — the user record is created or refreshed, and everything below is
   scoped to that user's id
1. **Understand** the topic → clean title, subject, difficulty, key concepts, prerequisites
2. **Explain** it at beginner level → definition, why it matters, how it works, an analogy
3. **Generate examples** (2–4)
4. **Generate a quiz** — 5 multiple-choice questions, 4 options each
5. **Pause** and wait for the student to answer in the browser
6. **Evaluate** — score computed deterministically in Python, qualitative feedback from the LLM
7. **Route on the result:**
   - score **< 70%** and retries remain → **re-explain more simply** + a shorter **3-question** quiz → back to step 4
   - score **≥ 70%**, or retries exhausted → **recommend the next topic** and finish

Loop guard: at most **2 retries** (`MAX_RETRIES`), so the cycle always terminates.
Thresholds live in one place — `graph/state.py` (`PASSING_SCORE`, `MAX_RETRIES`,
`FIRST_QUIZ_SIZE`, `RETRY_QUIZ_SIZE`).

---

## How it works

### Architecture

```
auth/  Google OAuth 2.0 + PKCE ─► UserContext(user_id) ─► db/ (SQLite: users, study_sessions)
   │
   ▼
app.py (Streamlit UI, gated by require_login())
   │  stream() / Command(resume=…)
   ▼
graph/workflow.py ── StateGraph, compiled with InMemorySaver (checkpointer)
   ├── graph/state.py    StudyState — the shared typed memory
   ├── graph/nodes.py    one function per step
   └── graph/edges.py    router for the conditional edge
          │
          ├── prompts/prompts.py   one ChatPromptTemplate per task
          ├── schemas/models.py    Pydantic models → structured LLM output
          ├── llm/model.py         ChatGroq clients, retries, error mapping
          └── utils/helpers.py     grading, quiz validation, logging (framework-free)
```

### The graph

```
START → understand_topic → generate_explanation → generate_examples → generate_quiz
      → wait_for_answers (interrupt)  → evaluate_answers
           ├─ score < 70 & retries left → re_explain_topic → back to generate_quiz
           └─ otherwise                 → recommend_next_topic → END
```

### Key mechanisms

- **Shared state** — `StudyState`, a `TypedDict`. Each node returns only the fields it
  changed; LangGraph merges the partial update.
- **Reducers** — `attempts` and `re_explanations` are `Annotated[list, operator.add]`, so
  returning a value *appends* to the history instead of overwriting it. Every graded
  attempt and every simpler explanation is preserved.
- **Human-in-the-loop** — `wait_for_answers` calls LangGraph's `interrupt()`. Execution
  stops, the checkpointer saves the state under a `thread_id`, and the UI renders the quiz.
  Submitting resumes with `Command(resume=answers)`, and `interrupt()` returns the answers.
- **Conditional routing** — `route_after_evaluation` in `graph/edges.py` reads `score` and
  `retry_count` and returns a label mapped to the next node.
- **Structured output** — each LLM call is a Pydantic schema (`.with_structured_output`), so
  nodes get validated objects, not free text to parse.
- **Deterministic grading** — the score is computed in Python from the stored correct
  answers; the LLM only writes the feedback. The model cannot mis-grade you.
- **Streamlit reruns** — the graph is built once via `@st.cache_resource`; LLM calls happen
  only on *Start Learning* and *Submit Quiz*. Every other rerun redraws from a copy of the
  state in `st.session_state`, so nothing is re-generated (and nothing is re-billed).

---

## Main features

**Tutoring**
- Topic analysis with prerequisites and difficulty
- Beginner explanation: definition, why it matters, how it works, an analogy
- 2–4 worked examples
- Auto-generated multiple-choice quizzes, validated before display
- Per-question explanations after submission
- Weak-concept tracking that feeds both the re-explanation and the next quiz
- Adaptive retry loop: simpler explanation + shorter quiz, capped at 2 retries
- Next-topic recommendation with the reason, clickable to start a new session

**Session history**
- Sidebar list of every past session, grouped Today / Yesterday / Previous 7 days / Older, most
  recent first, paged 15 at a time
- New session, open, rename and delete (with confirmation) from the sidebar; deleting the open one
  resets the workspace
- Reopening restores the LangGraph checkpoint, so a session paused mid-quiz can be continued
- A readable transcript is written to `session_messages` after each run, deterministically and
  append-only, so nothing is ever duplicated
- Titles come from the topic, upgraded to the `understand_topic` node's clean title; a manual
  rename is never overwritten

**Accounts and isolation**
- Google OAuth 2.0 authorization-code flow with PKCE (client id alone is enough; a client secret is
  sent only when one is configured), single-use CSRF state and ID token verification
- `users` table keyed on `google_id` (email is unique but never the identity key)
- Every user-scoped query filters on `user_id`; graph threads are namespaced `"<user_id>::<uuid4>"`
  and ownership-checked before any checkpoint read or resume
- Server-side sessions with expiry and revoking logout; the browser holds only an opaque session id
- Saved learning data (topics studied, attempts, average score) loaded at login
- Profile picture fetched server-side at login and inlined, with an initials fallback

**Engineering**
- Per-node Groq API keys (`GROQ_API_KEY_1` … `GROQ_API_KEY_8`) to spread rate limits, with a
  **backup key** for quiz generation and a single `GROQ_API_KEY` fallback for all of them
- Startup check that names exactly which keys are missing instead of crashing
- Retries and typed errors (`LLMError`, `MissingAPIKeyError`) around every model call
- Per-step **Retry this step** in the UI when a node fails, resuming the same thread
- `[GRAPH] / [NODE] / [ROUTER] / [LLM]` terminal logging, mirrored in a sidebar execution log
- Sidebar raw-state inspector (correct answers hidden while a quiz is open) and session reset
- Workflow viewer: the graph as text, Mermaid, or a rendered image

**UI**
- Green theme via `.streamlit/config.toml`
- Three.js 3D scenes: knowledge crystal, "thinking" knot during runs, animated score ring
  with trophy/confetti or seedling, rocket on the recommendation, and an interactive 3D map
  of the workflow highlighting visited and current nodes
- CSS animations: fade-in cards, progress stepper, flip cards, pill quiz options, balloons
  on pass — all disabled under "reduce motion"
- Offline-safe: if the Three.js CDN is unreachable, a CSS fallback renders and the app works

**Learning mode** — each layer runs standalone:
`python -m llm.model`, `python -m prompts.prompts`, `python -m graph.workflow` (full graph in
the terminal).

---

## Running it

```bash
cd ai-study-assistant
python -m venv .venv && .venv\Scripts\Activate.ps1   # Windows
pip install -r requirements.txt
copy .env.example .env      # add Groq key(s) and your Google OAuth client id
streamlit run app.py
```

`.env` and `*.db` are gitignored; keys and the OAuth client secret are loaded with `python-dotenv`
and never hard-coded. Run the tests with `python -m pytest tests -q`.

## Where to read more

- `README.md` — full setup, per-concept walkthrough, env-var table, example session transcript
- `LEARNING_GUIDE.md` — file-by-file teaching notes and a roadmap
