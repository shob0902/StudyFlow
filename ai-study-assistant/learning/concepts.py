# Concept identity. One vocabulary shared by quizzes, documents, reviews and coding practice,
# so every activity updates the same mastery row instead of keeping its own score.
import re
from dataclasses import dataclass
MAX_NAME_LENGTH = 80
DEFAULT_SUBJECT = "General"
# Words that carry no meaning in a concept name and would split one concept into several.
_NOISE = {
    "the", "a", "an", "of", "in", "on", "for", "to", "and", "or", "with", "about",
    "what", "is", "are", "how", "does", "do", "explain", "understanding", "introduction",
    "basics", "basic", "concept", "concepts", "topic", "intro",
}
# Subjects the app recognises, with the words that suggest them. Order matters: first match wins.
SUBJECT_HINTS: list[tuple[str, tuple[str, ...]]] = [
    ("Python", ("python", "pandas", "numpy", "django", "flask", "pytest", "decorator", "generator")),
    ("SQL", ("sql", "query", "join", "select", "database", "postgres", "mysql", "sqlite", "index")),
    ("DSA", (
        "algorithm", "data structure", "array", "linked list", "tree", "graph", "sorting",
        "search", "recursion", "dynamic programming", "hash", "stack", "queue", "heap",
        "complexity", "big o", "greedy", "backtracking",
    )),
    ("Machine Learning", (
        "machine learning", "neural", "regression", "classification", "clustering", "embedding",
        "gradient", "overfitting", "model", "training", "feature", "transformer", "llm",
    )),
    ("Web", ("html", "css", "javascript", "typescript", "react", "http", "api", "rest", "browser")),
    ("Systems", ("operating system", "process", "thread", "memory", "network", "tcp", "cache")),
    ("Mathematics", ("algebra", "calculus", "probability", "statistics", "matrix", "vector", "theorem")),
    ("Science", ("physics", "chemistry", "biology", "photosynthesis", "cell", "atom", "energy")),
]
# A concept as the app knows it: a display name, the subject it belongs to and a stable slug.
@dataclass(frozen=True)
class Concept:
    slug: str
    name: str
    subject: str
    # A concept is the same concept wherever it came from, so the slug is the identity.
    def __eq__(self, other: object) -> bool:
        return isinstance(other, Concept) and self.slug == other.slug
    def __hash__(self) -> int:
        return hash(self.slug)
# Strip a name down to the words that identify the concept.
def _significant_words(name: str) -> list[str]:
    words = re.findall(r"[a-z0-9+#]+", name.lower())
    kept = [word for word in words if word not in _NOISE]
    return kept or words
# The stable identifier for a concept: subject and name, normalised so the same idea written
# differently ("Binary Search", "binary search?", "the binary search") lands on one row.
def slugify(name: str, subject: str = DEFAULT_SUBJECT) -> str:
    words = _significant_words(name)
    body = "_".join(words)[:MAX_NAME_LENGTH] or "unknown"
    return f"{subject.strip().lower().replace(' ', '_')}::{body}"
# Guess the subject from the words in a concept or topic name.
def guess_subject(name: str, fallback: str = DEFAULT_SUBJECT) -> str:
    haystack = name.lower()
    for subject, hints in SUBJECT_HINTS:
        if any(hint in haystack for hint in hints):
            return subject
    return fallback
# Tidy a raw concept name coming from an LLM or a document into something worth displaying.
def clean_name(name: str) -> str:
    name = " ".join(str(name).split())
    name = name.strip(" .:-–—\"'")
    if not name:
        return ""
    if name.isupper() and len(name) > 4:
        name = name.title()
    elif name.islower():
        name = name.title()
    return name[:MAX_NAME_LENGTH]
# Build a Concept from a raw name, inferring the subject when one is not given.
def make_concept(name: str, subject: str = "") -> Concept | None:
    display = clean_name(name)
    if len(display) < 2:
        return None
    resolved = clean_name(subject) if subject else guess_subject(display)
    return Concept(slug=slugify(display, resolved), name=display, subject=resolved or DEFAULT_SUBJECT)
# Turn a list of raw names into unique concepts, keeping the order they arrived in.
def make_concepts(names: list[str], subject: str = "") -> list[Concept]:
    seen: set[str] = set()
    concepts = []
    for name in names:
        concept = make_concept(name, subject)
        if concept and concept.slug not in seen:
            seen.add(concept.slug)
            concepts.append(concept)
    return concepts
