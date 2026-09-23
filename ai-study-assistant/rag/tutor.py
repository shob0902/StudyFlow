# Answering from a student's own documents, and turning documents into quizzes, flashcards and
# concepts.
#
# Citations are built from the metadata of the passages actually retrieved — the model never
# supplies a filename, page or section. If a page number is unknown, the citation simply omits it
# rather than inventing one.
from dataclasses import dataclass
from typing import Any
from llm.model import NODE_API_KEYS, get_structured_llm, run_chain
from prompts.prompts import (
    DOCUMENT_ANSWER_PROMPT,
    DOCUMENT_CONCEPTS_PROMPT,
    DOCUMENT_QUIZ_PROMPT,
    FLASHCARD_PROMPT,
)
from rag.retriever import Hit
from rag.store import leading_chunks, search
from schemas.models import DocumentAnswer, DocumentConcepts, FlashcardSet, Quiz
from utils.helpers import LLMError, clean_quiz_questions, log_step
DEFAULT_PASSAGES = 5
QUIZ_PASSAGES = 8
# The ways a student can ask for the same material to be explained.
STYLES = {
    "explain": "Explain it clearly for someone studying this topic.",
    "beginner": "Explain it as if the student is a complete beginner. Short sentences, no jargon.",
    "summary": "Summarise the material faithfully, keeping the structure of the original.",
    "examples": "Give concrete examples drawn from the material.",
    "definitions": "Give the definitions exactly as the material states them.",
    "compare": "Compare and contrast the ideas the question asks about, using the material.",
    "notes": "Write tight revision notes as bullet points.",
}
# What a passage was, for citing it.
@dataclass(frozen=True)
class Citation:
    filename: str
    page: int | None = None
    section: str = ""
    # The citation as a single line. Only states what is actually known.
    def describe(self) -> str:
        parts = [self.filename or "Uploaded document"]
        if self.page:
            parts.append(f"Page {self.page}")
        if self.section:
            parts.append(f"Section: {self.section}")
        return " · ".join(parts)
# An answer plus the passages it was built from.
@dataclass(frozen=True)
class GroundedAnswer:
    answer: str
    citations: list[Citation]
    passages: list[Hit]
    confident: bool = True
    # True when nothing in the student's material was relevant.
    @property
    def is_empty(self) -> bool:
        return not self.passages
# Number the retrieved passages for the prompt, so the model can say which ones it used.
def format_passages(hits: list[Hit]) -> str:
    blocks = []
    for number, hit in enumerate(hits, start=1):
        where = hit.chunk.filename or "document"
        if hit.chunk.page:
            where += f", page {hit.chunk.page}"
        if hit.chunk.section:
            where += f", section {hit.chunk.section}"
        blocks.append(f"[{number}] ({where})\n{hit.chunk.content}")
    return "\n\n".join(blocks)
# Build citations from the passages the model said it used, falling back to all of them.
# Anything the model names that was not retrieved is ignored, so a citation cannot be invented.
def citations_for(hits: list[Hit], used: list[int]) -> list[Citation]:
    chosen = [hits[number - 1] for number in used if 1 <= number <= len(hits)] or hits
    seen: set[tuple] = set()
    citations = []
    for hit in chosen:
        key = (hit.chunk.filename, hit.chunk.page, hit.chunk.section)
        if key in seen:
            continue
        seen.add(key)
        citations.append(
            Citation(filename=hit.chunk.filename, page=hit.chunk.page, section=hit.chunk.section)
        )
    return citations
# Answer a question from the student's documents.
def answer_question(
    user_id: str, question: str, document_id: str = "", style: str = "explain",
    limit: int = DEFAULT_PASSAGES,
) -> GroundedAnswer:
    hits = search(user_id, question, document_id, limit)
    if not hits:
        return GroundedAnswer(
            answer=(
                "Nothing in your uploaded material covers that. Try rephrasing the question, or "
                "upload the document that deals with it."
            ),
            citations=[], passages=[], confident=False,
        )
    chain = DOCUMENT_ANSWER_PROMPT | get_structured_llm(
        DocumentAnswer, NODE_API_KEYS["document_tutor"]
    )
    result: DocumentAnswer = run_chain(
        chain,
        {
            "question": question,
            "style": STYLES.get(style, STYLES["explain"]),
            "passages": format_passages(hits),
        },
        "document answer",
    )
    log_step("RAG", f"Answered from {len(hits)} passage(s), model used {result.used_passages}")
    return GroundedAnswer(
        answer=result.answer,
        citations=citations_for(hits, result.used_passages),
        passages=hits,
        confident=result.confident,
    )
# Work out what a document teaches, to seed the knowledge graph.
def extract_concepts(user_id: str, document_id: str, filename: str) -> DocumentConcepts:
    chunks = leading_chunks(user_id, document_id, limit=10)
    if not chunks:
        return DocumentConcepts(subject="General", concepts=[], definitions=[], prerequisites=[])
    passages = "\n\n".join(chunk.content for chunk in chunks)
    chain = DOCUMENT_CONCEPTS_PROMPT | get_structured_llm(
        DocumentConcepts, NODE_API_KEYS["document_concepts"]
    )
    concepts: DocumentConcepts = run_chain(
        chain, {"filename": filename, "passages": passages[:12000]}, "document concepts"
    )
    log_step("RAG", f"{filename!r}: {len(concepts.concepts)} concept(s) in {concepts.subject}")
    return concepts
# Build a quiz from a document, reusing the same validation the topic quizzes use.
# The questions come back in exactly the shape the existing quiz UI and grader expect, which is
# what lets a document quiz feed the one mastery engine.
def quiz_from_document(
    user_id: str, document_id: str, filename: str, topic: str = "",
    num_questions: int = 5, difficulty: str = "medium",
) -> tuple[list[dict[str, Any]], list[Hit]]:
    from graph.nodes import DIFFICULTY_GUIDANCE
    hits = search(user_id, topic or filename, document_id, QUIZ_PASSAGES) if topic else []
    if not hits:
        chunks = leading_chunks(user_id, document_id, limit=QUIZ_PASSAGES)
        hits = [Hit(chunk=chunk, score=0.0) for chunk in chunks]
    if not hits:
        return [], []
    chain = DOCUMENT_QUIZ_PROMPT | get_structured_llm(Quiz, NODE_API_KEYS["document_quiz"])
    try:
        quiz: Quiz = run_chain(
            chain,
            {
                "filename": filename,
                "passages": format_passages(hits)[:14000],
                "num_questions": num_questions,
                "focus": topic or "the main ideas of this material",
                "difficulty": difficulty,
                "difficulty_guidance": DIFFICULTY_GUIDANCE.get(difficulty, ""),
            },
            "document quiz",
        )
    except LLMError:
        log_step("RAG", "Document quiz generation failed")
        raise
    questions = clean_quiz_questions([question.model_dump() for question in quiz.questions])
    log_step("RAG", f"Built {len(questions)} question(s) from {filename!r}")
    return questions[:num_questions], hits
# Turn material into revision cards for a review session.
def flashcards_from_document(
    user_id: str, document_id: str, topic: str = "", num_cards: int = 6
) -> tuple[FlashcardSet, list[Hit]]:
    hits = search(user_id, topic, document_id, DEFAULT_PASSAGES) if topic else []
    if not hits:
        chunks = leading_chunks(user_id, document_id, limit=DEFAULT_PASSAGES)
        hits = [Hit(chunk=chunk, score=0.0) for chunk in chunks]
    if not hits:
        return FlashcardSet(cards=[]), []
    chain = FLASHCARD_PROMPT | get_structured_llm(FlashcardSet, NODE_API_KEYS["flashcards"])
    cards: FlashcardSet = run_chain(
        chain,
        {
            "topic": topic or "this material",
            "passages": format_passages(hits)[:10000],
            "num_cards": num_cards,
        },
        "flashcards",
    )
    return cards, hits
