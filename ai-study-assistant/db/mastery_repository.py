# Storage for the knowledge graph: the shared concept vocabulary, each user's mastery and review
# schedule, the mistakes they make and the events behind the analytics.
# Every user-owned query filters on user_id, exactly like the rest of the data layer.
import json
import sqlite3
import uuid
from typing import Any
from auth.errors import DatabaseError
from db.models import utc_now
from learning.mastery import MasteryState
from learning.scheduling import ReviewState
from utils.helpers import log_error
# The shared concept vocabulary. Concepts are global; what a user knows about them is not.
class ConceptRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
    # Add a concept if it is new, and return its slug either way.
    def ensure(self, slug: str, name: str, subject: str) -> str:
        try:
            with self._connection:
                self._connection.execute(
                    "INSERT OR IGNORE INTO concepts (slug, name, subject, created_at) VALUES (?, ?, ?, ?)",
                    (slug, name, subject, utc_now()),
                )
        except sqlite3.Error:
            log_error("Could not store a concept")
            raise DatabaseError("Could not save what you just learnt. Please try again.")
        return slug
    # Look one concept up.
    def get(self, slug: str) -> dict[str, Any] | None:
        row = self._connection.execute("SELECT * FROM concepts WHERE slug = ?", (slug,)).fetchone()
        return dict(row) if row else None
    # Every concept in the vocabulary, for the knowledge view.
    def all(self, limit: int = 500) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT * FROM concepts ORDER BY subject, name LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]
# One user's mastery and review schedule, one row per concept.
class MasteryRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
    # Turn a stored row into the domain objects the algorithms work with.
    @staticmethod
    def _to_state(row: sqlite3.Row) -> MasteryState:
        return MasteryState(
            concept_slug=row["concept_slug"],
            concept_name=row["name"] if "name" in row.keys() else "",
            subject=row["subject"] if "subject" in row.keys() else "",
            mastery_score=row["mastery_score"],
            confidence=row["confidence"],
            attempts=row["attempts"],
            correct_attempts=row["correct_attempts"],
            incorrect_attempts=row["incorrect_attempts"],
            consecutive_correct=row["consecutive_correct"],
            consecutive_incorrect=row["consecutive_incorrect"],
            current_difficulty=row["current_difficulty"],
            last_attempted_at=row["last_attempted_at"],
            last_correct_at=row["last_correct_at"],
            learning_status=row["learning_status"],
        )
    # The review half of the same row.
    @staticmethod
    def _to_review(row: sqlite3.Row) -> ReviewState:
        return ReviewState(
            concept_slug=row["concept_slug"],
            interval_days=row["interval_days"],
            ease=row["ease"],
            review_count=row["review_count"],
            lapses=row["lapses"],
            last_reviewed_at=row["last_reviewed_at"],
            next_review_at=row["next_review_at"],
        )
    # One concept's mastery for this user, or None when they have never met it.
    def get(self, user_id: str, concept_slug: str) -> MasteryState | None:
        row = self._connection.execute(
            "SELECT m.*, c.name, c.subject FROM user_concept_mastery m"
            " JOIN concepts c ON c.slug = m.concept_slug"
            " WHERE m.user_id = ? AND m.concept_slug = ?",
            (user_id, concept_slug),
        ).fetchone()
        return self._to_state(row) if row else None
    # One concept's review schedule for this user.
    def get_review(self, user_id: str, concept_slug: str) -> ReviewState | None:
        row = self._connection.execute(
            "SELECT * FROM user_concept_mastery WHERE user_id = ? AND concept_slug = ?",
            (user_id, concept_slug),
        ).fetchone()
        return self._to_review(row) if row else None
    # Everything this user has studied, weakest first by default.
    def list_for_user(
        self, user_id: str, subject: str = "", limit: int = 500, order: str = "mastery_score ASC"
    ) -> list[MasteryState]:
        allowed = {
            "mastery_score ASC": "m.mastery_score ASC",
            "mastery_score DESC": "m.mastery_score DESC",
            "updated_at DESC": "m.updated_at DESC",
        }
        clause = allowed.get(order, "m.mastery_score ASC")
        if subject:
            rows = self._connection.execute(
                "SELECT m.*, c.name, c.subject FROM user_concept_mastery m"
                " JOIN concepts c ON c.slug = m.concept_slug"
                f" WHERE m.user_id = ? AND c.subject = ? ORDER BY {clause} LIMIT ?",
                (user_id, subject, limit),
            ).fetchall()
        else:
            rows = self._connection.execute(
                "SELECT m.*, c.name, c.subject FROM user_concept_mastery m"
                " JOIN concepts c ON c.slug = m.concept_slug"
                f" WHERE m.user_id = ? ORDER BY {clause} LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [self._to_state(row) for row in rows]
    # Mastery and review state together, which is what the review screen needs.
    def list_with_reviews(self, user_id: str, limit: int = 500) -> list[tuple[MasteryState, ReviewState]]:
        rows = self._connection.execute(
            "SELECT m.*, c.name, c.subject FROM user_concept_mastery m"
            " JOIN concepts c ON c.slug = m.concept_slug"
            " WHERE m.user_id = ? ORDER BY m.next_review_at ASC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [(self._to_state(row), self._to_review(row)) for row in rows]
    # Concepts whose review is due at or before the given moment.
    def due(self, user_id: str, before: str, limit: int = 50) -> list[tuple[MasteryState, ReviewState]]:
        rows = self._connection.execute(
            "SELECT m.*, c.name, c.subject FROM user_concept_mastery m"
            " JOIN concepts c ON c.slug = m.concept_slug"
            " WHERE m.user_id = ? AND m.next_review_at != '' AND m.next_review_at <= ?"
            " ORDER BY m.mastery_score ASC, m.next_review_at ASC LIMIT ?",
            (user_id, before, limit),
        ).fetchall()
        return [(self._to_state(row), self._to_review(row)) for row in rows]
    # Write a concept's mastery and schedule back. Inserts on first contact, updates afterwards.
    def save(self, user_id: str, state: MasteryState, review: ReviewState | None = None) -> None:
        now = utc_now()
        review = review or ReviewState(concept_slug=state.concept_slug)
        try:
            with self._connection:
                self._connection.execute(
                    "INSERT INTO user_concept_mastery ("
                    " user_id, concept_slug, mastery_score, confidence, attempts, correct_attempts,"
                    " incorrect_attempts, consecutive_correct, consecutive_incorrect, current_difficulty,"
                    " learning_status, last_attempted_at, last_correct_at, interval_days, ease,"
                    " review_count, lapses, last_reviewed_at, next_review_at, created_at, updated_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
                    " ON CONFLICT(user_id, concept_slug) DO UPDATE SET"
                    " mastery_score=excluded.mastery_score, confidence=excluded.confidence,"
                    " attempts=excluded.attempts, correct_attempts=excluded.correct_attempts,"
                    " incorrect_attempts=excluded.incorrect_attempts,"
                    " consecutive_correct=excluded.consecutive_correct,"
                    " consecutive_incorrect=excluded.consecutive_incorrect,"
                    " current_difficulty=excluded.current_difficulty,"
                    " learning_status=excluded.learning_status,"
                    " last_attempted_at=excluded.last_attempted_at,"
                    " last_correct_at=excluded.last_correct_at,"
                    " interval_days=excluded.interval_days, ease=excluded.ease,"
                    " review_count=excluded.review_count, lapses=excluded.lapses,"
                    " last_reviewed_at=excluded.last_reviewed_at,"
                    " next_review_at=excluded.next_review_at, updated_at=excluded.updated_at",
                    (
                        user_id, state.concept_slug, state.mastery_score, state.confidence,
                        state.attempts, state.correct_attempts, state.incorrect_attempts,
                        state.consecutive_correct, state.consecutive_incorrect,
                        state.current_difficulty, state.learning_status, state.last_attempted_at,
                        state.last_correct_at, review.interval_days, review.ease,
                        review.review_count, review.lapses, review.last_reviewed_at,
                        review.next_review_at, now, now,
                    ),
                )
        except sqlite3.Error:
            log_error("Could not save mastery")
            raise DatabaseError("Could not save your progress on this concept. Please try again.")
    # How many concepts this user has practised.
    def count(self, user_id: str) -> int:
        row = self._connection.execute(
            "SELECT COUNT(*) AS n FROM user_concept_mastery WHERE user_id = ?", (user_id,)
        ).fetchone()
        return int(row["n"])
# The mistakes a user makes, kept per concept so the next explanation can address them.
class MistakeRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
    # Record one mistake.
    def add(self, user_id: str, concept_slug: str, category: str, note: str = "", source: str = "quiz") -> None:
        try:
            with self._connection:
                self._connection.execute(
                    "INSERT INTO concept_mistakes (id, user_id, concept_slug, category, note, source, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), user_id, concept_slug, category, note[:400], source, utc_now()),
                )
        except sqlite3.Error:
            log_error("Could not record a mistake")
    # This user's recent mistakes on a concept.
    def for_concept(self, user_id: str, concept_slug: str, limit: int = 10) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT * FROM concept_mistakes WHERE user_id = ? AND concept_slug = ?"
            " ORDER BY created_at DESC LIMIT ?",
            (user_id, concept_slug, limit),
        ).fetchall()
        return [dict(row) for row in rows]
    # This user's recent mistakes across every concept.
    def recent(self, user_id: str, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT * FROM concept_mistakes WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]
# Every learning action, for analytics and for the study streak.
class EventRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
    # Record one event.
    def add(
        self, user_id: str, kind: str, concept_slug: str = "", activity: str = "",
        correct: bool | None = None, score: float | None = None, detail: dict | None = None,
    ) -> None:
        try:
            with self._connection:
                self._connection.execute(
                    "INSERT INTO learning_events"
                    " (id, user_id, kind, concept_slug, activity, correct, score, detail, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        str(uuid.uuid4()), user_id, kind, concept_slug, activity,
                        None if correct is None else int(correct), score,
                        json.dumps(detail or {}), utc_now(),
                    ),
                )
        except sqlite3.Error:
            log_error("Could not record a learning event")
    # This user's recent events.
    def recent(self, user_id: str, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._connection.execute(
            "SELECT * FROM learning_events WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]
    # Accuracy for one kind of activity, used by the dashboard.
    def accuracy(self, user_id: str, activity: str) -> tuple[int, int]:
        row = self._connection.execute(
            "SELECT COUNT(*) AS total, SUM(COALESCE(correct, 0)) AS correct"
            " FROM learning_events WHERE user_id = ? AND activity = ? AND correct IS NOT NULL",
            (user_id, activity),
        ).fetchone()
        return int(row["correct"] or 0), int(row["total"] or 0)
    # The distinct days this user did something, newest first, for the streak.
    def active_days(self, user_id: str, limit: int = 60) -> list[str]:
        rows = self._connection.execute(
            "SELECT DISTINCT substr(created_at, 1, 10) AS day FROM learning_events"
            " WHERE user_id = ? ORDER BY day DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [row["day"] for row in rows]
