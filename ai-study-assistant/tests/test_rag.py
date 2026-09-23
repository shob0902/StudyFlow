# The document tutor: extraction, chunking, retrieval, citations, isolation and document quizzes.
import pytest
from auth.errors import UnauthorizedError
from rag import store
from rag.extract import DocumentError, ExtractedBlock, clean_text, extract, kind_for, validate
from rag.retriever import BM25Retriever, Chunk, chunk_blocks, tokenize
from rag.tutor import Citation, citations_for, format_passages
NOTES = b"""# Binary Search

Binary search finds a target inside a sorted array by repeatedly halving the range.
It runs in logarithmic time because each comparison discards half of the candidates.

# Dynamic Programming

Dynamic programming solves problems that have overlapping subproblems by storing results.
Memoization caches results from the top down, while tabulation fills a table from the bottom up.
Optimal substructure is the requirement that makes this work at all.
"""
# A signed-in user with one document.
@pytest.fixture
def library(users, db_file):
    user = users.upsert_from_google("google-1", "ada@example.com", "Ada")
    document = store.ingest(user.id, "notes.md", NOTES)
    return user, document
# --- extraction ---------------------------------------------------------
# The supported file types are recognised by extension.
def test_supported_types():
    assert kind_for("notes.pdf") == "pdf"
    assert kind_for("notes.TXT") == "txt"
    assert kind_for("notes.md") == "md"
    assert kind_for("report.docx") == "docx"
    with pytest.raises(DocumentError):
        kind_for("photo.png")
    with pytest.raises(DocumentError):
        kind_for("noextension")
# Empty and oversized files are refused before any work happens.
def test_bad_files_are_refused():
    with pytest.raises(DocumentError):
        validate("notes.txt", b"")
    with pytest.raises(DocumentError):
        validate("notes.txt", b"x" * (21 * 1024 * 1024))
# A file with almost no text is refused with an explanation.
def test_empty_document_is_refused():
    with pytest.raises(DocumentError) as error:
        extract("notes.txt", b"hi")
    assert "readable text" in str(error.value)
# Markdown headings become section names on the blocks under them.
def test_headings_become_sections():
    document = extract("notes.md", NOTES)
    sections = {block.section for block in document.blocks}
    assert "Binary Search" in sections
    assert "Dynamic Programming" in sections
# Extraction tidies the whitespace and the hyphenation PDFs leave behind.
def test_text_is_cleaned():
    assert clean_text("some-\nthing") == "something"
    assert clean_text("a   b\n\n\n\nc") == "a b\n\nc"
# --- chunking -----------------------------------------------------------
# Chunks carry the page and section they came from, which is what citations are built from.
def test_chunks_keep_their_origin():
    blocks = [ExtractedBlock(text="word " * 400, page=7, section="Intro")]
    chunks = chunk_blocks(blocks, size=100, overlap=20)
    assert len(chunks) > 1
    assert all(chunk.page == 7 and chunk.section == "Intro" for chunk in chunks)
    assert [chunk.position for chunk in chunks] == list(range(len(chunks)))
# Chunks overlap so a sentence on a boundary is still findable.
def test_chunks_overlap():
    blocks = [ExtractedBlock(text=" ".join(str(number) for number in range(300)))]
    chunks = chunk_blocks(blocks, size=100, overlap=20)
    first_words = set(chunks[0].content.split())
    second_words = set(chunks[1].content.split())
    assert first_words & second_words
# --- retrieval ----------------------------------------------------------
# Common words are ignored when matching.
def test_tokenizer_drops_noise():
    assert tokenize("What is the binary search?") == ["binary", "search"]
# BM25 ranks the passage that actually answers the question first.
def test_retriever_finds_the_right_passage():
    chunks = [
        Chunk(content="Binary search halves a sorted range each step.", position=0),
        Chunk(content="Memoization caches results from the top down.", position=1),
        Chunk(content="A queue is first in, first out.", position=2),
    ]
    retriever = BM25Retriever()
    retriever.index(chunks)
    hits = retriever.search("how does memoization cache results")
    assert hits[0].chunk.position == 1
    assert hits[0].score > 0
# A query with nothing to match returns nothing rather than a bad guess.
def test_retriever_returns_nothing_for_no_match():
    retriever = BM25Retriever()
    retriever.index([Chunk(content="Binary search halves the range.", position=0)])
    assert retriever.search("quantum chromodynamics") == []
    assert retriever.search("") == []
# --- storing and searching ---------------------------------------------
# An uploaded document is chunked and stored.
def test_ingest_stores_chunks(library):
    _user, document = library
    assert document.filename == "notes.md"
    assert document.chunk_count >= 1
    assert document.status == "ready"
# Searching finds the passage from the right section.
def test_search_finds_the_section(library):
    user, _document = library
    hits = store.search(user.id, "what is memoization")
    assert hits
    assert "Memoization" in hits[0].chunk.content
    assert hits[0].chunk.section == "Dynamic Programming"
    assert hits[0].chunk.filename == "notes.md"
# Uploading the same file twice is refused rather than duplicated.
def test_duplicate_upload_is_refused(library):
    user, _document = library
    with pytest.raises(DocumentError):
        store.ingest(user.id, "notes.md", NOTES)
    assert len(store.list_documents(user.id)) == 1
# Deleting a document takes its chunks with it.
def test_delete_removes_chunks(library, connection):
    user, document = library
    assert store.delete_document(user.id, document.id) is True
    remaining = connection.execute(
        "SELECT COUNT(*) AS n FROM document_chunks WHERE document_id = ?", (document.id,)
    ).fetchone()["n"]
    assert remaining == 0
    assert store.search(user.id, "memoization") == []
# --- isolation ----------------------------------------------------------
# One user's documents are invisible to another.
def test_documents_are_private(library, users):
    owner, document = library
    other = users.upsert_from_google("google-2", "bob@example.com", "Bob")
    assert store.list_documents(other.id) == []
    assert store.get_document(other.id, document.id) is None
    assert store.search(other.id, "memoization") == []
    assert store.delete_document(other.id, document.id) is False
# Searching inside someone else's document is refused outright.
def test_cannot_search_inside_another_users_document(library, users):
    _owner, document = library
    other = users.upsert_from_google("google-2", "bob@example.com", "Bob")
    with pytest.raises(UnauthorizedError):
        store.search(other.id, "memoization", document.id)
# Nobody can upload or search without signing in.
def test_signed_out_access_is_refused(db_file):
    with pytest.raises(UnauthorizedError):
        store.ingest("", "notes.md", NOTES)
    with pytest.raises(UnauthorizedError):
        store.search("", "anything")
# --- citations ----------------------------------------------------------
# A citation states only what the document metadata actually says.
def test_citations_state_only_what_is_known():
    assert Citation("Notes.pdf", 42, "Trees").describe() == "Notes.pdf · Page 42 · Section: Trees"
    assert Citation("Notes.pdf", None, "").describe() == "Notes.pdf"
    assert Citation("Notes.pdf", None, "Trees").describe() == "Notes.pdf · Section: Trees"
# Citations are built from the passages retrieved, so a page number cannot be invented.
def test_citations_come_from_real_passages():
    hits = _fake_hits()
    cited = citations_for(hits, [2])
    assert len(cited) == 1
    assert cited[0].filename == "Book.pdf"
    assert cited[0].page == 9
# A passage number the model made up is ignored rather than cited.
def test_invented_passage_numbers_are_ignored():
    hits = _fake_hits()
    cited = citations_for(hits, [99, 2])
    assert [c.page for c in cited] == [9]
    # If the model cites nothing usable, the retrieved passages are cited instead.
    assert len(citations_for(hits, [99])) == 2
# Passages are numbered for the prompt so the model can refer to them.
def test_passages_are_numbered_for_the_prompt():
    text = format_passages(_fake_hits())
    assert "[1]" in text and "[2]" in text
    assert "page 4" in text
# Two hits from one file with page numbers.
def _fake_hits():
    from rag.retriever import Hit
    return [
        Hit(chunk=Chunk(content="first", position=0, page=4, section="A", filename="Book.pdf"), score=2.0),
        Hit(chunk=Chunk(content="second", position=1, page=9, section="B", filename="Book.pdf"), score=1.0),
    ]
# --- document quizzes ---------------------------------------------------
# A quiz built from a document goes through the same validation as a topic quiz.
def test_document_quiz_uses_the_shared_validation(library, monkeypatch):
    from schemas.models import Quiz, QuizQuestion
    import rag.tutor as tutor
    user, document = library
    good = QuizQuestion(
        question="What does memoization do?",
        options=["Caches results", "Sorts data", "Frees memory", "Opens files"],
        correct_answer="Caches results",
        explanation="It stores results of subproblems.",
    )
    broken = QuizQuestion(
        question="Bad", options=["a", "a", "b", "c"], correct_answer="zzz", explanation=""
    )
    from langchain_core.runnables import RunnableLambda
    monkeypatch.setattr(
        tutor, "get_structured_llm", lambda *a, **k: RunnableLambda(lambda value: value)
    )
    monkeypatch.setattr(tutor, "run_chain", lambda *a, **k: Quiz(questions=[good, broken]))
    questions, hits = tutor.quiz_from_document(user.id, document.id, "notes.md", num_questions=5)
    assert len(questions) == 1
    assert questions[0]["correct_answer"] in questions[0]["options"]
    assert hits
