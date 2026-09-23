# Builds and compiles the StateGraph, with a terminal demo of the full workflow.
import sqlite3
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from graph.edges import RE_EXPLAIN, RECOMMEND, route_after_evaluation
from graph.nodes import (
    evaluate_answers,
    generate_examples,
    generate_explanation,
    generate_quiz,
    re_explain_topic,
    recommend_next_topic,
    understand_topic,
    wait_for_answers,
)
from graph.knowledge import update_knowledge
from graph.state import StudyState
from utils.helpers import log_step
UNDERSTAND_TOPIC = "understand_topic"
GENERATE_EXPLANATION = "generate_explanation"
GENERATE_EXAMPLES = "generate_examples"
GENERATE_QUIZ = "generate_quiz"
WAIT_FOR_ANSWERS = "wait_for_answers"
EVALUATE_ANSWERS = "evaluate_answers"
UPDATE_KNOWLEDGE = "update_knowledge"
RE_EXPLAIN_TOPIC = "re_explain_topic"
RECOMMEND_NEXT_TOPIC = "recommend_next_topic"
NODE_LABELS = {
    UNDERSTAND_TOPIC: "Understood the topic",
    GENERATE_EXPLANATION: "Wrote the explanation",
    GENERATE_EXAMPLES: "Created examples",
    GENERATE_QUIZ: "Generated a quiz",
    WAIT_FOR_ANSWERS: "Received your answers",
    EVALUATE_ANSWERS: "Evaluated your answers",
    UPDATE_KNOWLEDGE: "Updated your mastery",
    RE_EXPLAIN_TOPIC: "Wrote a simpler explanation",
    RECOMMEND_NEXT_TOPIC: "Recommended a next topic",
}
TEXT_DIAGRAM = """\
START
 ↓
Understand Topic
 ↓
Explanation
 ↓
Examples
 ↓
Quiz  ←──────────────┐
 ↓                   │
Wait for Answers     │  (graph pauses here)
 ↓                   │
Evaluation           │
 ↓                   │
Update Mastery       │  (concepts, misconceptions, review schedule)
 ├── Weak → Re-explain ┘   (max 2 retries)
 └── Ready → Next Topic → END
"""
# The checkpointer that keeps graph state on disk, so a paused quiz survives a restart and a
# session reopened from the history can carry on exactly where it stopped.
def sqlite_checkpointer() -> SqliteSaver:
    from db.database import checkpoint_path
    connection = sqlite3.connect(checkpoint_path(), check_same_thread=False)
    log_step("GRAPH", f"Checkpoints stored in {checkpoint_path()!r}")
    return SqliteSaver(connection)
# Create the StateGraph, add nodes and edges, and compile it with a checkpointer.
def build_workflow(checkpointer: BaseCheckpointSaver | None = None) -> CompiledStateGraph:
    log_step("GRAPH", "Building workflow")
    builder = StateGraph(StudyState)
    builder.add_node(UNDERSTAND_TOPIC, understand_topic)
    builder.add_node(GENERATE_EXPLANATION, generate_explanation)
    builder.add_node(GENERATE_EXAMPLES, generate_examples)
    builder.add_node(GENERATE_QUIZ, generate_quiz)
    builder.add_node(WAIT_FOR_ANSWERS, wait_for_answers)
    builder.add_node(EVALUATE_ANSWERS, evaluate_answers)
    builder.add_node(UPDATE_KNOWLEDGE, update_knowledge)
    builder.add_node(RE_EXPLAIN_TOPIC, re_explain_topic)
    builder.add_node(RECOMMEND_NEXT_TOPIC, recommend_next_topic)
    builder.add_edge(START, UNDERSTAND_TOPIC)
    builder.add_edge(UNDERSTAND_TOPIC, GENERATE_EXPLANATION)
    builder.add_edge(GENERATE_EXPLANATION, GENERATE_EXAMPLES)
    builder.add_edge(GENERATE_EXAMPLES, GENERATE_QUIZ)
    builder.add_edge(GENERATE_QUIZ, WAIT_FOR_ANSWERS)
    builder.add_edge(WAIT_FOR_ANSWERS, EVALUATE_ANSWERS)
    builder.add_edge(EVALUATE_ANSWERS, UPDATE_KNOWLEDGE)
    builder.add_conditional_edges(
        UPDATE_KNOWLEDGE,
        route_after_evaluation,
        {
            RE_EXPLAIN: RE_EXPLAIN_TOPIC,
            RECOMMEND: RECOMMEND_NEXT_TOPIC,
        },
    )
    builder.add_edge(RE_EXPLAIN_TOPIC, GENERATE_QUIZ)
    builder.add_edge(RECOMMEND_NEXT_TOPIC, END)
    return builder.compile(checkpointer=checkpointer or sqlite_checkpointer())
# Return the Mermaid source for the compiled graph.
def get_mermaid_diagram(graph: CompiledStateGraph) -> str:
    return graph.get_graph().draw_mermaid()
if __name__ == "__main__":
    import uuid
    from langgraph.types import Command
    from graph.state import create_initial_state
    from utils.helpers import StudyAssistantError
    # Ask in the terminal until the user types a number from 1 to 4.
    def ask_choice() -> int:
        while True:
            choice = input("Your answer (1-4): ").strip()
            if choice in {"1", "2", "3", "4"}:
                return int(choice)
            print("Please type a number from 1 to 4.")
    graph = build_workflow()
    print(TEXT_DIAGRAM)
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    graph_input: object = create_initial_state(input("What do you want to learn? "))
    while True:
        try:
            graph.invoke(graph_input, config)
        except StudyAssistantError as error:
            raise SystemExit(f"Error: {error}")
        snapshot = graph.get_state(config)
        if not snapshot.next:
            break
        answers = []
        for number, question in enumerate(snapshot.values["quiz"], start=1):
            print(f"\nQ{number}. {question['question']}")
            for index, option in enumerate(question["options"], start=1):
                print(f"   {index}) {option}")
            answers.append(question["options"][ask_choice() - 1])
        graph_input = Command(resume=answers)
    final = graph.get_state(config).values
    print(f"\nFinal score: {final['score']:.0f}%")
    print(f"Recommended next topic: {final['next_topic']}")
    print(final["recommendation"]["reason"])
