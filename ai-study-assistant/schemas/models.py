# Pydantic models describing the structured output expected from the LLM.
from pydantic import BaseModel, Field
class TopicAnalysis(BaseModel):
    """A short analysis of what the student wants to learn."""
    clean_topic: str = Field(
        description="The topic rewritten as a short, clear title, e.g. 'Embeddings'."
    )
    subject_area: str = Field(
        description="The broader field this topic belongs to, e.g. 'Machine Learning'."
    )
    difficulty: str = Field(
        description="One of: beginner, intermediate, advanced."
    )
    key_concepts: list[str] = Field(
        description="3 to 5 core concepts a beginner must understand for this topic."
    )
    prerequisites: list[str] = Field(
        description="0 to 3 topics that are helpful to know before this one."
    )
class Explanation(BaseModel):
    """A beginner-friendly explanation of a topic."""
    definition: str = Field(
        description="A simple 1-3 sentence definition with no unexplained jargon."
    )
    why_it_matters: str = Field(
        description="Why this topic is useful or important in the real world."
    )
    how_it_works: str = Field(
        description="A step-by-step, plain-language description of how it works."
    )
    analogy: str = Field(
        description="A simple everyday analogy that makes the idea intuitive."
    )
    key_points: list[str] = Field(
        description="3 to 5 short bullet points summarising the most important ideas."
    )
class Example(BaseModel):
    """One concrete example of the topic."""
    title: str = Field(description="A short title for the example.")
    description: str = Field(
        description="2-4 sentences describing the example and how it shows the topic."
    )
class ExampleSet(BaseModel):
    """A list of concrete examples."""
    examples: list[Example] = Field(description="Between 2 and 4 examples.")
class QuizQuestion(BaseModel):
    """One multiple-choice quiz question."""
    question: str = Field(description="The question text.")
    options: list[str] = Field(
        description="Exactly 4 answer options. Do NOT prefix them with A), B), 1., etc."
    )
    correct_answer: str = Field(
        description="The correct option, copied EXACTLY from the options list."
    )
    explanation: str = Field(
        description="1-2 sentences explaining why the correct answer is right."
    )
class Quiz(BaseModel):
    """A multiple-choice quiz."""
    questions: list[QuizQuestion] = Field(description="The quiz questions.")
class Evaluation(BaseModel):
    """Personalised feedback on a student's quiz attempt."""
    overall_feedback: str = Field(
        description="2-3 encouraging sentences about how the student did."
    )
    strengths: list[str] = Field(
        description="Concepts the student clearly understands (can be empty)."
    )
    weak_concepts: list[str] = Field(
        description="Specific concepts the student is struggling with (can be empty)."
    )
    study_tip: str = Field(description="One practical tip for what to do next.")
class Recommendation(BaseModel):
    """A recommendation for what the student should learn next."""
    summary: str = Field(
        description="1-2 sentences summarising the student's understanding of the topic."
    )
    next_topic: str = Field(description="The recommended next topic, as a short title.")
    reason: str = Field(description="Why this topic is a good next step.")
    extra_guidance: list[str] = Field(
        description=(
            "Additional study guidance. Give 2-4 items if the student did not pass, "
            "otherwise it can be empty."
        )
    )
class DocumentAnswer(BaseModel):
    """An answer grounded in the student's own uploaded material."""
    answer: str = Field(description="The answer, written for the student, using only the passages given.")
    used_passages: list[int] = Field(
        default_factory=list,
        description="The numbers of the passages actually used, e.g. [1, 3]. Empty if none applied.",
    )
    confident: bool = Field(
        default=True, description="False if the passages do not really answer the question."
    )
class DocumentConcepts(BaseModel):
    """What a document is about."""
    subject: str = Field(description="The single subject area this document belongs to.")
    concepts: list[str] = Field(description="3-12 concept names a student would need to learn.")
    definitions: list[str] = Field(
        default_factory=list, description="Key definitions, each as 'term: meaning'."
    )
    prerequisites: list[str] = Field(
        default_factory=list, description="Concepts a student should already know."
    )
class Flashcard(BaseModel):
    """One two-sided revision card."""
    front: str = Field(description="The prompt side: a question or term.")
    back: str = Field(description="The answer side, one or two sentences.")
    concept: str = Field(default="", description="The concept this card tests.")
class FlashcardSet(BaseModel):
    """A set of revision cards."""
    cards: list[Flashcard] = Field(description="Between 3 and 10 cards.")
class CodingProblemSpec(BaseModel):
    """A generated coding problem with everything needed to solve and grade it."""
    title: str = Field(description="A short title.")
    statement: str = Field(description="The problem statement, including what to return.")
    constraints: str = Field(default="", description="Input sizes and value ranges.")
    signature: str = Field(description="The exact function signature to implement, e.g. 'def solve(nums: list[int]) -> int:'")
    function_name: str = Field(description="The function name the tests will call.")
    examples: list[str] = Field(
        default_factory=list, description="Worked examples as 'input -> output' lines."
    )
    test_inputs: list[str] = Field(
        description="Python literal argument tuples, e.g. '([1, 2, 3], 2)'. One per test case."
    )
    test_outputs: list[str] = Field(
        description="The expected return value for each test, as a Python literal. Same order and length as test_inputs."
    )
    concepts: list[str] = Field(description="The concepts this problem exercises, e.g. ['binary search', 'arrays'].")
class CodingHint(BaseModel):
    """One step of progressive help, without giving the answer away early."""
    hint: str = Field(description="The help at this level only. Never include full working code unless asked for the solution.")
class CodeReview(BaseModel):
    """Analysis of a submission that passed its tests."""
    time_complexity: str = Field(description="Big-O time complexity of the submitted code.")
    space_complexity: str = Field(description="Big-O auxiliary space of the submitted code.")
    reasoning: str = Field(description="One or two sentences explaining those complexities from the code.")
    improvement: str = Field(default="", description="A concrete possible optimisation, or empty if it is already optimal.")
    edge_cases: list[str] = Field(default_factory=list, description="Edge cases worth checking.")
class FailureAnalysis(BaseModel):
    """Why a submission failed, in one line the student can act on."""
    likely_issue: str = Field(description="The most likely cause, e.g. 'Edge case when the array has one element.'")
    hint: str = Field(description="A nudge towards the fix, without writing the fix.")
class StudyPlanTopics(BaseModel):
    """The topics a subject should be broken into for a study plan."""
    subject: str = Field(description="The subject, tidied up.")
    topics: list[str] = Field(description="6-16 topic names in a sensible learning order.")
