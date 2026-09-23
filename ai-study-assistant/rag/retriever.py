# Chunking and retrieval.
#
# Retrieval sits behind a small interface. The implementation shipped here is BM25 over the
# user's own chunks: it is deterministic, needs no model download and no embedding API, and it
# runs offline. Swapping in real vector embeddings means writing another Retriever with the same
# two methods — nothing else in the app has to change. See README for what that involves.
import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable, Protocol
CHUNK_WORDS = 180
CHUNK_OVERLAP_WORDS = 40
MIN_CHUNK_WORDS = 25
_TOKEN = re.compile(r"[a-z0-9]+")
# Very common words carry no signal for retrieval.
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from", "has", "have", "how",
    "in", "into", "is", "it", "its", "of", "on", "or", "that", "the", "their", "then", "there",
    "these", "this", "to", "was", "were", "what", "when", "which", "who", "why", "will", "with",
    "you", "your", "can", "does", "do", "if", "not", "we", "they", "he", "she", "i",
}
# A piece of a document, with where it came from.
@dataclass(frozen=True)
class Chunk:
    content: str
    position: int
    page: int | None = None
    section: str = ""
    document_id: str = ""
    filename: str = ""
    # Words in the chunk.
    @property
    def word_count(self) -> int:
        return len(self.content.split())
# A chunk the retriever picked, and how well it matched.
@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float
# What any retrieval backend must provide. A vector store would implement exactly this.
class Retriever(Protocol):
    def index(self, chunks: Iterable[Chunk]) -> None: ...
    def search(self, query: str, limit: int = 5) -> list[Hit]: ...
# Split text into retrieval-sized chunks, carrying page and section through.
# Chunks overlap so a sentence spanning a boundary is still findable from either side.
def chunk_blocks(
    blocks: Iterable[Any], size: int = CHUNK_WORDS, overlap: int = CHUNK_OVERLAP_WORDS
) -> list[Chunk]:
    chunks: list[Chunk] = []
    position = 0
    for block in blocks:
        words = str(block.text).split()
        if not words:
            continue
        step = max(1, size - overlap)
        start = 0
        while start < len(words):
            window = words[start : start + size]
            # Do not leave a stub at the end; fold it into the previous chunk instead.
            if len(window) < MIN_CHUNK_WORDS and chunks and start > 0:
                break
            chunks.append(
                Chunk(
                    content=" ".join(window),
                    position=position,
                    page=getattr(block, "page", None),
                    section=getattr(block, "section", "") or "",
                )
            )
            position += 1
            start += step
    return chunks
# Split a query or a chunk into the words worth matching on.
def tokenize(text: str) -> list[str]:
    return [word for word in _TOKEN.findall(str(text).lower()) if word not in STOPWORDS and len(word) > 1]
# BM25 ranking over a set of chunks held in memory.
#
# BM25 rewards a chunk for containing the query's rarer words, without letting a long chunk win
# just by being long. k1 controls how quickly repeated words stop helping; b how hard length is
# normalised.
class BM25Retriever:
    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self._chunks: list[Chunk] = []
        self._tokens: list[list[str]] = []
        self._frequencies: list[Counter] = []
        self._document_frequency: Counter = Counter()
        self._average_length = 0.0
    # Build the index. Cheap enough to rebuild per query set for a personal library.
    def index(self, chunks: Iterable[Chunk]) -> None:
        self._chunks = list(chunks)
        self._tokens = [tokenize(chunk.content) for chunk in self._chunks]
        self._frequencies = [Counter(tokens) for tokens in self._tokens]
        self._document_frequency = Counter()
        for tokens in self._tokens:
            for token in set(tokens):
                self._document_frequency[token] += 1
        lengths = [len(tokens) for tokens in self._tokens]
        self._average_length = sum(lengths) / len(lengths) if lengths else 0.0
    # How rare a word is across the indexed chunks.
    def _idf(self, token: str) -> float:
        total = len(self._chunks)
        seen = self._document_frequency.get(token, 0)
        if total == 0 or seen == 0:
            return 0.0
        return math.log(1 + (total - seen + 0.5) / (seen + 0.5))
    # The best-matching chunks for a query, best first.
    def search(self, query: str, limit: int = 5) -> list[Hit]:
        terms = tokenize(query)
        if not terms or not self._chunks:
            return []
        scored: list[Hit] = []
        for index, frequencies in enumerate(self._frequencies):
            length = len(self._tokens[index]) or 1
            score = 0.0
            for term in terms:
                count = frequencies.get(term, 0)
                if not count:
                    continue
                numerator = count * (self.k1 + 1)
                denominator = count + self.k1 * (
                    1 - self.b + self.b * length / (self._average_length or length)
                )
                score += self._idf(term) * numerator / denominator
            if score > 0:
                scored.append(Hit(chunk=self._chunks[index], score=round(score, 4)))
        scored.sort(key=lambda hit: hit.score, reverse=True)
        return scored[:limit]
    def __len__(self) -> int:
        return len(self._chunks)
# Build a retriever over the given chunks. One place to change when swapping the backend.
def build_retriever(chunks: Iterable[Chunk]) -> Retriever:
    retriever = BM25Retriever()
    retriever.index(chunks)
    return retriever
