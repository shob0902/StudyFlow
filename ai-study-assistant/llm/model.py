# Creates one ChatGroq model per API key and runs LangChain calls with retries and safe errors.
import os
from functools import lru_cache
from typing import Any
import groq
from dotenv import load_dotenv
from langchain_core.exceptions import OutputParserException
from langchain_core.runnables import Runnable
from langchain_groq import ChatGroq
from pydantic import BaseModel, ValidationError
from utils.helpers import LLMError, MissingAPIKeyError, log_step
load_dotenv()
MODEL = "openai/gpt-oss-120b"
TEMPERATURE = 0.4
_PLACEHOLDER_KEY = "your_groq_api_key_here"
NODE_API_KEYS = {
    "understand_topic": "GROQ_API_KEY_1",
    "generate_explanation": "GROQ_API_KEY_2",
    "generate_examples": "GROQ_API_KEY_3",
    "generate_quiz": "GROQ_API_KEY_4",
    "generate_quiz_backup": "GROQ_API_KEY_5",
    "evaluate_answers": "GROQ_API_KEY_6",
    "re_explain_topic": "GROQ_API_KEY_7",
    "recommend_next_topic": "GROQ_API_KEY_8",
    # The platform features reuse the same eight keys rather than asking for more: each one is
    # mapped to the node whose load it most resembles.
    "document_tutor": "GROQ_API_KEY_2",
    "document_concepts": "GROQ_API_KEY_1",
    "document_quiz": "GROQ_API_KEY_4",
    "flashcards": "GROQ_API_KEY_3",
    "coding_problem": "GROQ_API_KEY_3",
    "coding_hint": "GROQ_API_KEY_7",
    "coding_review": "GROQ_API_KEY_6",
    "study_planner": "GROQ_API_KEY_8",
}
# The eight keys the app asks the user to configure. The extra entries above are aliases onto
# these, so a missing-key check never demands a key that does not exist.
PRIMARY_NODES = (
    "understand_topic", "generate_explanation", "generate_examples", "generate_quiz",
    "generate_quiz_backup", "evaluate_answers", "re_explain_topic", "recommend_next_topic",
)
FALLBACK_KEY = "GROQ_API_KEY"
# Read an environment variable, treating empty values and placeholders as missing.
def _read_key(key_name: str) -> str | None:
    value = os.getenv(key_name, "").strip()
    return value if value and value != _PLACEHOLDER_KEY else None
# Return the key for a variable name, falling back to GROQ_API_KEY.
def get_api_key(key_name: str) -> str:
    key = _read_key(key_name) or _read_key(FALLBACK_KEY)
    if key is None:
        raise MissingAPIKeyError(
            f"{key_name} is missing. Copy .env.example to .env and add your Groq API keys."
        )
    return key
# List node key names that have no value and no fallback.
def missing_api_keys() -> list[str]:
    if _read_key(FALLBACK_KEY):
        return []
    required = [NODE_API_KEYS[node] for node in PRIMARY_NODES]
    return [key_name for key_name in required if not _read_key(key_name)]
# Create and cache one ChatGroq model per API key name.
@lru_cache(maxsize=None)
def get_llm(key_name: str = "GROQ_API_KEY_1") -> ChatGroq:
    return ChatGroq(
        model=MODEL,
        temperature=TEMPERATURE,
        api_key=get_api_key(key_name),
        max_retries=2,
        timeout=60,
    )
# Send a plain text prompt to Groq and return the text answer.
def ask_llm(prompt: str) -> str:
    llm = get_llm()
    log_step("LLM", f"ask_llm: {prompt[:60]!r}")
    try:
        response = llm.invoke(prompt)
    except groq.APIError as error:
        raise LLMError(_friendly_groq_message(error)) from error
    return str(response.content)
# Return a model using the given key that answers with the Pydantic schema.
def get_structured_llm(schema: type[BaseModel], key_name: str) -> Runnable:
    log_step("LLM", f"Using {key_name} for {schema.__name__}")
    return get_llm(key_name).with_structured_output(schema, method="json_schema", strict=True)
# Invoke a chain, retrying invalid output and converting Groq errors to LLMError.
def run_chain(
    chain: Runnable,
    inputs: dict[str, Any],
    step_name: str,
    attempts: int = 2,
) -> Any:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        log_step("LLM", f"Calling Groq for '{step_name}' (attempt {attempt}/{attempts})")
        try:
            result = chain.invoke(inputs)
            if result is None:
                raise ValueError("The model returned an empty response.")
            return result
        except (OutputParserException, ValidationError, ValueError, groq.BadRequestError) as error:
            last_error = error
            log_step("LLM", f"Invalid output for '{step_name}': {type(error).__name__}. Retrying...")
        except groq.APIError as error:
            raise LLMError(_friendly_groq_message(error)) from error
    raise LLMError(
        f"The AI returned an unexpected response while working on '{step_name}'. "
        "Please try again."
    ) from last_error
# Map a Groq SDK exception to a short, non-sensitive message.
def _friendly_groq_message(error: groq.APIError) -> str:
    if isinstance(error, groq.AuthenticationError):
        return "Groq rejected an API key. Please check the GROQ_API_KEY_* values in your .env file."
    if isinstance(error, groq.RateLimitError):
        return "Groq rate limit reached. Please wait a moment and try again."
    if isinstance(error, groq.APIConnectionError):
        return "Could not reach the Groq API. Please check your internet connection."
    if isinstance(error, groq.APIStatusError):
        return f"The Groq API returned an error (status {error.status_code}). Please try again."
    return "An unexpected error occurred while calling the Groq API."
if __name__ == "__main__":
    try:
        answer = ask_llm("Explain what an embedding is in two sentences, for a beginner.")
        print("\n--- Groq answer ---\n")
        print(answer)
    except (MissingAPIKeyError, LLMError) as error:
        print(f"Error: {error}")
