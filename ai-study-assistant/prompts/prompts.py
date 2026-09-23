# LangChain ChatPromptTemplates, one small prompt per study task.
from langchain_core.prompts import ChatPromptTemplate
TUTOR_SYSTEM = (
    "You are a patient, friendly tutor who explains things to complete beginners. "
    "Use simple words, short sentences and concrete everyday examples. "
    "Avoid jargon; if you must use a technical term, explain it immediately."
)
TOPIC_ANALYSIS_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", TUTOR_SYSTEM),
        (
            "human",
            "A student wants to learn about the following:\n\n"
            "\"{topic}\"\n\n"
            "Analyse this request. Give the topic a clean short title, identify its "
            "subject area, estimate its difficulty, list the key concepts a beginner "
            "must understand, and list any helpful prerequisites.",
        ),
    ]
)
EXPLANATION_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", TUTOR_SYSTEM),
        (
            "human",
            "Explain the topic \"{topic}\" to a beginner.\n\n"
            "Make sure the explanation covers these key concepts:\n{key_concepts}\n\n"
            "Include a clear definition, why it matters, how it works step by step, "
            "and a simple everyday analogy.",
        ),
    ]
)
EXAMPLES_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", TUTOR_SYSTEM),
        (
            "human",
            "The student just read this explanation of \"{topic}\":\n\n"
            "{explanation}\n\n"
            "Give 3 concrete, varied, real-world examples that make the topic easy "
            "to picture. Keep each example short.",
        ),
    ]
)
QUIZ_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You write clear multiple-choice quizzes that check real understanding, "
            "not memorisation of exact wording.",
        ),
        (
            "human",
            "Create exactly {num_questions} multiple-choice questions about \"{topic}\" "
            "based on this explanation:\n\n{explanation}\n\n"
            "Focus: {focus}\n\n"
            "Difficulty: {difficulty}\n{difficulty_guidance}\n\n"
            "Do not repeat these earlier questions:\n{avoid_questions}\n\n"
            "Rules:\n"
            "- Each question has exactly 4 options.\n"
            "- Exactly one option is correct.\n"
            "- Do not prefix options with letters or numbers.\n"
            "- correct_answer must be copied exactly from the options.\n"
            "- Wrong options should be plausible, not silly.\n"
            "- Match the stated difficulty.",
        ),
    ]
)
EVALUATION_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", TUTOR_SYSTEM),
        (
            "human",
            "A student took a quiz about \"{topic}\" and scored {score}%.\n\n"
            "Here are their results:\n{results}\n\n"
            "Look at the mistakes and identify which underlying concepts the student "
            "is struggling with (not just which questions were wrong). Also note what "
            "they clearly understand. Be encouraging and specific.",
        ),
    ]
)
RE_EXPLANATION_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", TUTOR_SYSTEM),
        (
            "human",
            "A student did not pass a quiz about \"{topic}\" (re-explanation #{attempt}).\n\n"
            "This is the explanation they already read:\n{previous_explanation}\n\n"
            "They are struggling with:\n{weak_concepts}\n\n"
            "Explain the topic again in a SIMPLER and DIFFERENT way. Focus especially "
            "on the concepts they struggle with. Use a new analogy, shorter sentences, "
            "and no jargon at all.",
        ),
    ]
)
RECOMMENDATION_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", TUTOR_SYSTEM),
        (
            "human",
            "A student has finished studying \"{topic}\".\n"
            "Final quiz score: {score}%\n"
            "Passed: {passed}\n\n"
            "Strengths:\n{strengths}\n\n"
            "Weak concepts:\n{weak_concepts}\n\n"
            "Known prerequisites for this topic:\n{prerequisites}\n\n"
            "If the student PASSED: recommend a natural next topic that builds on "
            "this one, and explain why.\n"
            "If the student did NOT pass after several attempts: be kind, recommend a "
            "simpler foundational topic that will help them come back to this one, "
            "and give practical extra guidance for studying.",
        ),
    ]
)
# Answer a question using only the student's own uploaded passages.
DOCUMENT_ANSWER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a patient tutor answering from the student's own study material. "
            "Use ONLY the passages provided. If they do not answer the question, say so plainly "
            "and set confident to false. Never invent page numbers, sources or facts.",
        ),
        (
            "human",
            "Question: {question}\n\n"
            "Style: {style}\n\n"
            "Passages from the student's documents:\n{passages}\n\n"
            "Answer the question using only these passages. "
            "List in used_passages the numbers of the passages you actually relied on.",
        ),
    ]
)
# Work out what a document is about, to seed the knowledge graph.
DOCUMENT_CONCEPTS_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You catalogue study material. You name concepts the way a syllabus would: short, "
            "specific noun phrases. You never invent content that is not in the text.",
        ),
        (
            "human",
            "Here are extracts from a document called \"{filename}\":\n\n{passages}\n\n"
            "Identify the subject, the concepts a student must learn, key definitions and any "
            "prerequisites. Keep concept names under six words.",
        ),
    ]
)
# Write a quiz from the student's own material.
DOCUMENT_QUIZ_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You write multiple-choice questions that test understanding of a specific document. "
            "Every question must be answerable from the passages given.",
        ),
        (
            "human",
            "Create exactly {num_questions} multiple-choice questions from these passages of "
            "\"{filename}\":\n\n{passages}\n\n"
            "Focus: {focus}\n"
            "Difficulty: {difficulty}\n{difficulty_guidance}\n\n"
            "Rules:\n"
            "- Each question has exactly 4 options.\n"
            "- Exactly one option is correct.\n"
            "- Do not prefix options with letters or numbers.\n"
            "- correct_answer must be copied exactly from the options.\n"
            "- Only ask what the passages actually support.",
        ),
    ]
)
# Turn material into revision cards.
FLASHCARD_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", "You make revision flashcards: one idea per card, short and precise."),
        (
            "human",
            "Make {num_cards} flashcards about \"{topic}\" from this material:\n\n{passages}\n\n"
            "The front is a question or term; the back is the answer in one or two sentences.",
        ),
    ]
)
# Invent a coding problem for a concept at a difficulty.
CODING_PROBLEM_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You set programming exercises. Your problems are precise, self-contained and "
            "testable by calling a single function. Test inputs and outputs must be valid Python "
            "literals, and every expected output must be exactly what the correct solution returns.",
        ),
        (
            "human",
            "Write one {difficulty} {language} problem about \"{topic}\".\n"
            "{difficulty_guidance}\n\n"
            "Requirements:\n"
            "- One function the tests call, with a clear signature.\n"
            "- Between 4 and 8 test cases, including at least one edge case.\n"
            "- test_inputs are argument tuples as Python literals, e.g. '([1, 2, 3], 5)'.\n"
            "- A single-argument call still needs a tuple, e.g. '([1, 2, 3],)'.\n"
            "- test_outputs are the expected return values as Python literals.\n"
            "- Do not include the solution anywhere.",
        ),
    ]
)
# Progressive help on a coding problem: one level at a time.
CODING_HINT_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a coach who refuses to hand over answers early. You give exactly the level "
            "of help asked for and no more.",
        ),
        (
            "human",
            "Problem:\n{statement}\n\n"
            "The student's current code:\n```\n{code}\n```\n\n"
            "What happened when it ran: {outcome}\n\n"
            "Give help at level {level} of 5, which means: {level_meaning}\n"
            "Do not go beyond that level.",
        ),
    ]
)
# Explain why a submission failed, from its real test results.
CODING_FAILURE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You diagnose failing code from its actual test results. You never guess beyond the "
            "evidence, and you never write the corrected code.",
        ),
        (
            "human",
            "Problem:\n{statement}\n\nThe student's code:\n```\n{code}\n```\n\n"
            "Results: {passed} of {total} tests passed.\n"
            "Failing cases:\n{failures}\n\n"
            "Name the single most likely issue and give one nudge towards it.",
        ),
    ]
)
# Analyse a working submission.
CODE_REVIEW_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You analyse submitted code. You state complexity only from what the code actually "
            "does — the loops, recursion and data structures in front of you.",
        ),
        (
            "human",
            "Problem:\n{statement}\n\nThe student's working solution:\n```\n{code}\n```\n\n"
            "Give its time and space complexity, explain briefly how the code leads to them, "
            "suggest one concrete improvement if there is one, and list edge cases worth testing.",
        ),
    ]
)
# Break a subject into an ordered topic list for a study plan.
STUDY_PLAN_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You design syllabi. You order topics so each one builds on the last, and you keep "
            "names short and specific.",
        ),
        (
            "human",
            "Build a topic list for a student studying \"{subject}\".\n"
            "Current level: {level}\n"
            "Time available: {weeks} weeks at {hours_per_day} hours a day\n"
            "They specifically want: {wanted}\n"
            "They are already strong at: {strong}\n"
            "They are weak at: {weak}\n\n"
            "Return topics in the order they should be studied. Put weak areas early.",
        ),
    ]
)
if __name__ == "__main__":
    messages = EXPLANATION_PROMPT.invoke(
        {"topic": "Embeddings", "key_concepts": "- vectors\n- similarity"}
    ).to_messages()
    for message in messages:
        print(f"--- {message.type.upper()} ---\n{message.content}\n")
