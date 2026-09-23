# Animated HTML cards rendered with st.html; every LLM-generated string is HTML-escaped first.
import html
from typing import Any
# Escape text for safe HTML and keep its line breaks.
def esc(text: Any) -> str:
    return html.escape(str(text)).replace("\n", "<br>")
# Build a row of chip badges, optionally styled good or warn.
def chips(items: list[str], kind: str = "") -> str:
    return "<div class='sa-chips'>" + "".join(
        f"<span class='sa-chip {kind}'>{esc(item)}</span>" for item in items
    ) + "</div>"
# Hero text: badge, animated gradient title, tagline and feature chips.
def hero_intro() -> str:
    return (
        "<div class='sa-hero'>"
        "<span class='sa-badge'>LANGCHAIN · LANGGRAPH · GROQ</span>"
        "<div class='sa-title'>AI Study Assistant</div>"
        "<p class='sa-sub'>Pick any topic. Learn it, see it in action, test yourself, and level up.</p>"
        "<div class='sa-chips'>"
        "<span class='sa-chip'>Learn</span>"
        "<span class='sa-chip' style='animation-delay:.1s'>Explore</span>"
        "<span class='sa-chip' style='animation-delay:.2s'>Quiz</span>"
        "<span class='sa-chip' style='animation-delay:.3s'>Grow</span>"
        "</div></div>"
    )
# Progress stepper showing which study stages are done, active or still to come.
def stepper(steps: list[tuple[str, str, str]]) -> str:
    parts = []
    for index, (icon, label, state) in enumerate(steps):
        if index:
            parts.append("<span class='sa-arrow'>›</span>")
        parts.append(f"<div class='sa-step {state}'><span class='dot'>{icon}</span>{esc(label)}</div>")
    return "<div class='sa-stepper'>" + "".join(parts) + "</div>"
# Topic card with subject, difficulty and key concept chips.
def topic_card(analysis: dict[str, Any]) -> str:
    return (
        "<div class='sa-card' style='margin:.9rem 0'>"
        "<div class='sa-topic'>"
        f"<div><div class='sa-badge'>{esc(analysis.get('subject_area', ''))}</div>"
        f"<div class='name'>{esc(analysis.get('clean_topic', ''))}</div></div>"
        f"<span class='sa-chip good'>{esc(analysis.get('difficulty', ''))}</span>"
        "</div>"
        "<div class='sa-label'>Key concepts</div>"
        f"{chips(analysis.get('key_concepts', []))}"
        "</div>"
    )
# Explanation as animated tiles: definition, why it matters, how it works, analogy and key points.
def explanation_cards(explanation: dict[str, Any], simpler: bool = False) -> str:
    extra = " sa-simpler" if simpler else ""
    tiles = [
        ("Definition", explanation.get("definition", ""), extra),
        ("Why it matters", explanation.get("why_it_matters", ""), extra),
        ("How it works", explanation.get("how_it_works", ""), extra),
        ("Simple analogy", explanation.get("analogy", ""), " sa-analogy"),
    ]
    body = "".join(
        f"<div class='sa-card{css}'><h4>{title}</h4><p>{esc(text)}</p></div>"
        for title, text, css in tiles
    )
    points = explanation.get("key_points") or []
    key_points = f"<div class='sa-label'>Key points</div>{chips(points, 'good')}" if points else ""
    return f"<div class='sa-grid'>{body}</div>{key_points}"
# Examples as 3D flip cards that turn over on hover or tap.
def example_cards(examples: list[dict[str, Any]]) -> str:
    cards = []
    for index, example in enumerate(examples):
        cards.append(
            f"<div class='sa-flip' tabindex='0' style='animation-delay:{index * 0.12:.2f}s'>"
            "<div class='sa-flip-inner'>"
            f"<div class='sa-face sa-front'><div class='num'>{index + 1:02d}</div>"
            f"<div class='ttl'>{esc(example.get('title', ''))}</div>"
            "<div class='hint'>hover or tap to flip</div></div>"
            f"<div class='sa-face sa-back'><b>{esc(example.get('title', ''))}</b>{esc(example.get('description', ''))}</div>"
            "</div></div>"
        )
    return "<div class='sa-flip-grid'>" + "".join(cards) + "</div>"
# Friendly intro banner shown above the quiz form.
def quiz_intro(num_questions: int, passing_score: int, is_retry: bool) -> str:
    title = "A shorter quiz on the tricky parts" if is_retry else "Time to test yourself!"
    return (
        f"<div class='sa-quiz-intro'><span class='big'>{num_questions}</span><div>"
        f"<div style='font-weight:900;font-size:1.1rem'>{title}</div>"
        f"<div>{num_questions} questions · score {passing_score}% or more to pass</div>"
        "</div></div>"
    )
# Score tiles, pass/retry banner, strengths, weak concepts, feedback and study tip for one attempt.
def result_summary(attempt: dict[str, Any], max_retries: int) -> str:
    correct = attempt["correct_count"]
    incorrect = attempt["total_questions"] - correct
    if attempt["passed"]:
        banner = "<div class='sa-banner pass'>Great job! You understand the fundamentals of this topic.</div>"
    elif attempt["attempt_number"] > max_retries:
        banner = "<div class='sa-banner stop'>You've used all retries. That's okay, let's move forward with extra guidance.</div>"
    else:
        banner = "<div class='sa-banner retry'>Let's revisit the topic with a simpler explanation.</div>"
    parts = [
        "<div class='sa-tiles'>"
        f"<div class='sa-tile'><div class='num'>{attempt['score']:.0f}%</div><div class='lbl'>Your score</div></div>"
        f"<div class='sa-tile'><div class='num'>{correct}</div><div class='lbl'>Correct</div></div>"
        f"<div class='sa-tile bad'><div class='num'>{incorrect}</div><div class='lbl'>Incorrect</div></div>"
        "</div>",
        banner,
    ]
    if not attempt["passed"] and attempt.get("weak_concepts"):
        parts.append(f"<div class='sa-label'>You seem to be struggling with</div>{chips(attempt['weak_concepts'], 'warn')}")
    if attempt.get("strengths"):
        parts.append(f"<div class='sa-label'>What you already understand</div>{chips(attempt['strengths'], 'good')}")
    parts.append(f"<div class='sa-card' style='margin-top:.8rem'><h4>Feedback</h4><p>{esc(attempt.get('overall_feedback', ''))}</p></div>")
    if attempt.get("study_tip"):
        parts.append(f"<div class='sa-card sa-analogy' style='margin-top:.6rem'><h4>Tip</h4><p>{esc(attempt['study_tip'])}</p></div>")
    return "".join(parts)
# Per-question result cards with the student's answer, the correct answer and the explanation.
def question_results(results: list[dict[str, Any]]) -> str:
    cards = []
    for index, result in enumerate(results, start=1):
        right = result["is_correct"]
        cards.append(
            f"<div class='sa-result {'' if right else 'wrong'}' style='animation-delay:{index * 0.06:.2f}s'>"
            f"<div class='q'><span class='icon'>{'Correct' if right else 'Incorrect'}</span>Q{index}. {esc(result['question'])}</div>"
            f"<div class='ans'>Your answer: <b>{esc(result['user_answer'])}</b><br>Correct answer: <b>{esc(result['correct_answer'])}</b></div>"
            f"<div class='why'>{esc(result['explanation'])}</div>"
            "</div>"
        )
    return "".join(cards)
# Glowing next-topic card with summary, reason and extra guidance.
def recommendation_card(recommendation: dict[str, Any], passed: bool) -> str:
    guidance = recommendation.get("extra_guidance") or []
    guidance_html = (
        "<div class='sa-label'>Extra guidance</div><ul style='margin:.2rem 0 0 1.1rem'>"
        + "".join(f"<li>{esc(item)}</li>" for item in guidance)
        + "</ul>"
        if guidance
        else ""
    )
    kicker = "You leveled up! Recommended next topic" if passed else "Recommended next step"
    return (
        "<div class='sa-next'><div class='sa-next-inner'>"
        f"<div class='kicker'>{kicker}</div>"
        f"<div class='topic'>{esc(recommendation.get('next_topic', ''))}</div>"
        f"<p style='margin:.2rem 0 .6rem'>{esc(recommendation.get('summary', ''))}</p>"
        f"<div class='sa-label'>Why this topic?</div><p style='margin:0'>{esc(recommendation.get('reason', ''))}</p>"
        f"{guidance_html}"
        "</div></div>"
    )
# Gradient sidebar header with the model and quiz settings.
def sidebar_header(model: str, passing_score: int, max_retries: int) -> str:
    return (
        "<div class='sa-side-head'>"
        "<div class='t'>AI Study Assistant</div>"
        f"<div class='sa-side-row'><span>Model</span><span>{esc(model)}</span></div>"
        f"<div class='sa-side-row'><span>Quiz passing score</span><span>{passing_score}%</span></div>"
        f"<div class='sa-side-row' style='border:none'><span>Maximum retries</span><span>{max_retries}</span></div>"
        "</div>"
    )
# Sidebar rows describing the current study session.
def sidebar_session(rows: list[tuple[str, str]]) -> str:
    return "<div class='sa-card' style='padding:.7rem 1rem'>" + "".join(
        f"<div class='sa-side-row'><span>{esc(label)}</span><span>{esc(value)}</span></div>" for label, value in rows
    ) + "</div>"
# Friendly names for the parts of a saved session transcript.
TRANSCRIPT_LABELS = {
    "topic": "You asked",
    "explanation": "Explanation",
    "examples": "Examples",
    "quiz": "Quiz",
    "answers": "Your answers",
    "results": "Results",
    "re_explanation": "Simpler explanation",
    "recommendation": "What's next",
}
# One saved transcript line, drawn as a chat-style bubble.
def transcript_message(role: str, kind: str, content: str) -> str:
    label = TRANSCRIPT_LABELS.get(kind, kind.replace("_", " ").title())
    side = "user" if role == "user" else "assistant"
    return (
        f"<div class='sa-msg {side}'>"
        f"<div class='sa-msg-label'>{esc(label)}</div>"
        f"<div class='sa-msg-body'>{esc(content)}</div>"
        "</div>"
    )
# The whole saved transcript of a session.
def transcript(messages: list[Any]) -> str:
    return "<div class='sa-transcript'>" + "".join(
        transcript_message(message.role, message.kind, message.content) for message in messages
    ) + "</div>"
# A labelled mastery bar, coloured by how solid the concept is.
def mastery_bar(label: str, score: float, status: str = "") -> str:
    band = status if status in ("weak", "learning") else ""
    width = max(0.0, min(100.0, float(score)))
    return (
        f"<div class='sa-bar {band}'><span class='lbl'>{esc(label)}</span>"
        f"<span class='track'><span class='fill' style='width:{width:.0f}%'></span></span>"
        f"<span class='val'>{width:.0f}%</span></div>"
    )
# A row of headline numbers.
def metrics(items: list[tuple[str, Any, str]]) -> str:
    cells = []
    for label, value, sub in items:
        warn = "warn" if isinstance(value, str) and value.endswith("!") else ""
        cells.append(
            f"<div class='sa-metric {warn}'><div class='v'>{esc(str(value).rstrip('!'))}</div>"
            f"<div class='k'>{esc(label)}</div>"
            + (f"<div class='sub'>{esc(sub)}</div>" if sub else "")
            + "</div>"
        )
    return "<div class='sa-metrics'>" + "".join(cells) + "</div>"
# A small status pill for a concept.
def status_pill(status: str) -> str:
    return f"<span class='sa-pill {esc(status)}'>{esc(status.replace('_', ' '))}</span>"
# The source line under an answer drawn from the user's documents.
def citation(text: str) -> str:
    return f"<div class='sa-cite'><b>Source:</b> {esc(text)}</div>"
# One concept waiting to be reviewed. The urgency reads as a coloured word, not a coloured dot.
def due_row(urgency: str, name: str, detail: str) -> str:
    band = str(urgency).lower()
    return (
        f"<div class='sa-due'><span class='sa-pill {esc(band)}'>{esc(urgency)}</span>"
        f"<span class='nm'>{esc(name)}</span>"
        f"<span style='font-size:.8rem;opacity:.7'>{esc(detail)}</span></div>"
    )
# How the student's code will be run, stated plainly.
def sandbox_notice(level: str, message: str) -> str:
    return f"<div class='sa-sandbox {esc(level)}'>{esc(message)}</div>"
