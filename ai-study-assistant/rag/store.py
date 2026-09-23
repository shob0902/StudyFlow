# Storing and searching a user's documents. Every query here is scoped to one user_id: a
# document id alone never grants access.
import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from typing import Any
from auth.errors import DatabaseError, UnauthorizedError
from db.database import session
from db.models import utc_now
from rag.extract import DocumentError, extract
from rag.retriever import Chunk, Hit, build_retriever, chunk_blocks
from utils.helpers import log_error, log_step
MAX_SEARCH_CHUNKS = 4000
# A stored document.
@dataclass(frozen=True)
class Document:
    id: str
    user_id: str
    filename: str
    content_type: str
    size_bytes: int
    pages: int
    chunk_count: int
    status: str
    error: str
    concepts: list[str]
    created_at: str
    # Build from a database row.
    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Document":
        try:
            concepts = json.loads(row["concepts"] or "[]")
        except json.JSONDecodeError:
            concepts = []
        return cls(
            id=row["id"], user_id=row["user_id"], filename=row["filename"],
            content_type=row["content_type"], size_bytes=row["size_bytes"], pages=row["pages"],
            chunk_count=row["chunk_count"], status=row["status"], error=row["error"],
            concepts=concepts, created_at=row["created_at"],
        )
# The fingerprint used to spot a re-upload of the same file.
def checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
# Documents and their chunks, always for one user.
class DocumentRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
    # This user's documents, newest first.
    def list_for_user(self, user_id: str, limit: int = 50) -> list[Document]:
        rows = self._connection.execute(
            "SELECT * FROM documents WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [Document.from_row(row) for row in rows]
    # One of this user's documents, or None when it is not theirs.
    def get(self, user_id: str, document_id: str) -> Document | None:
        row = self._connection.execute(
            "SELECT * FROM documents WHERE id = ? AND user_id = ?", (document_id, user_id)
        ).fetchone()
        return Document.from_row(row) if row else None
    # A document this user already uploaded with the same contents.
    def find_by_checksum(self, user_id: str, digest: str) -> Document | None:
        row = self._connection.execute(
            "SELECT * FROM documents WHERE user_id = ? AND checksum = ?", (user_id, digest)
        ).fetchone()
        return Document.from_row(row) if row else None
    # Store a document and its chunks in one transaction, so a half-ingested file cannot linger.
    def create(
        self, user_id: str, filename: str, content_type: str, data: bytes,
        pages: int, chunks: list[Chunk],
    ) -> Document:
        document_id = str(uuid.uuid4())
        now = utc_now()
        try:
            with self._connection:
                self._connection.execute(
                    "INSERT INTO documents (id, user_id, filename, content_type, size_bytes,"
                    " checksum, pages, chunk_count, status, error, concepts, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ready', '', '[]', ?)",
                    (
                        document_id, user_id, filename[:200], content_type, len(data),
                        checksum(data), pages, len(chunks), now,
                    ),
                )
                self._connection.executemany(
                    "INSERT INTO document_chunks"
                    " (id, document_id, user_id, position, page, section, content, word_count)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        (
                            str(uuid.uuid4()), document_id, user_id, chunk.position, chunk.page,
                            chunk.section, chunk.content, chunk.word_count,
                        )
                        for chunk in chunks
                    ],
                )
        except sqlite3.IntegrityError:
            raise DocumentError("You have already uploaded this file.")
        except sqlite3.Error:
            log_error("Could not store a document")
            raise DatabaseError("Could not save that document. Please try again.")
        return self.get(user_id, document_id)  # type: ignore[return-value]
    # Record the concepts found in a document.
    def set_concepts(self, user_id: str, document_id: str, concepts: list[str]) -> None:
        if self.get(user_id, document_id) is None:
            raise UnauthorizedError("That document does not belong to your account.")
        with self._connection:
            self._connection.execute(
                "UPDATE documents SET concepts = ? WHERE id = ? AND user_id = ?",
                (json.dumps(concepts[:40]), document_id, user_id),
            )
    # Delete a document and, by cascade, its chunks.
    def delete(self, user_id: str, document_id: str) -> bool:
        with self._connection:
            cursor = self._connection.execute(
                "DELETE FROM documents WHERE id = ? AND user_id = ?", (document_id, user_id)
            )
        return cursor.rowcount > 0
    # The chunks to search: this user's, optionally narrowed to one document they own.
    def chunks_for_search(
        self, user_id: str, document_id: str = "", limit: int = MAX_SEARCH_CHUNKS
    ) -> list[Chunk]:
        if document_id:
            if self.get(user_id, document_id) is None:
                raise UnauthorizedError("That document does not belong to your account.")
            rows = self._connection.execute(
                "SELECT c.*, d.filename FROM document_chunks c JOIN documents d ON d.id = c.document_id"
                " WHERE c.user_id = ? AND c.document_id = ? ORDER BY c.position LIMIT ?",
                (user_id, document_id, limit),
            ).fetchall()
        else:
            rows = self._connection.execute(
                "SELECT c.*, d.filename FROM document_chunks c JOIN documents d ON d.id = c.document_id"
                " WHERE c.user_id = ? ORDER BY c.document_id, c.position LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [
            Chunk(
                content=row["content"], position=row["position"], page=row["page"],
                section=row["section"] or "", document_id=row["document_id"],
                filename=row["filename"],
            )
            for row in rows
        ]
    # How many documents this user has.
    def count(self, user_id: str) -> int:
        row = self._connection.execute(
            "SELECT COUNT(*) AS n FROM documents WHERE user_id = ?", (user_id,)
        ).fetchone()
        return int(row["n"])
# Take an uploaded file all the way to searchable chunks.
# Validate -> extract -> chunk -> store. Embedding would slot in between chunk and store.
def ingest(user_id: str, filename: str, data: bytes, content_type: str = "") -> Document:
    if not user_id:
        raise UnauthorizedError("Please sign in before uploading documents.")
    extracted = extract(filename, data)
    chunks = chunk_blocks(extracted.blocks)
    if not chunks:
        raise DocumentError(f"'{filename}' produced no readable text to study.")
    with session() as connection:
        repository = DocumentRepository(connection)
        existing = repository.find_by_checksum(user_id, checksum(data))
        if existing is not None:
            raise DocumentError(f"You have already uploaded '{existing.filename}'.")
        document = repository.create(
            user_id, filename, content_type, data, extracted.pages, chunks
        )
    log_step("RAG", f"Stored {filename!r} as {len(chunks)} chunks for user {user_id}")
    return document
# This user's documents.
def list_documents(user_id: str, limit: int = 50) -> list[Document]:
    with session() as connection:
        return DocumentRepository(connection).list_for_user(user_id, limit)
# One of this user's documents.
def get_document(user_id: str, document_id: str) -> Document | None:
    with session() as connection:
        return DocumentRepository(connection).get(user_id, document_id)
# Delete one of this user's documents.
def delete_document(user_id: str, document_id: str) -> bool:
    with session() as connection:
        return DocumentRepository(connection).delete(user_id, document_id)
# Record the concepts extracted from a document.
def set_document_concepts(user_id: str, document_id: str, concepts: list[str]) -> None:
    with session() as connection:
        DocumentRepository(connection).set_concepts(user_id, document_id, concepts)
# Find the passages that answer a question, within what this user owns.
def search(user_id: str, query: str, document_id: str = "", limit: int = 5) -> list[Hit]:
    if not user_id:
        raise UnauthorizedError("Please sign in to search your documents.")
    with session() as connection:
        chunks = DocumentRepository(connection).chunks_for_search(user_id, document_id)
    if not chunks:
        return []
    return build_retriever(chunks).search(query, limit)
# The opening passages of a document, for summarising and concept extraction.
def leading_chunks(user_id: str, document_id: str, limit: int = 12) -> list[Chunk]:
    with session() as connection:
        chunks = DocumentRepository(connection).chunks_for_search(user_id, document_id)
    return chunks[:limit]
