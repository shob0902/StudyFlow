# Running a student's code against test cases.
#
# SECURITY: running code someone typed is the most dangerous thing this app does, so execution
# sits behind one interface with two implementations:
#
#   DockerRunner     - a throwaway container with no network, a read-only filesystem, a memory
#                      cap and a pid cap. This is the one to use when code is not your own.
#   SubprocessRunner - a separate, short-lived interpreter process with a wall-clock timeout, a
#                      scrubbed environment and a temporary working directory. It is process
#                      isolation, NOT a security boundary: the code still runs as your user and
#                      can read files and open sockets. Acceptable only for code you wrote
#                      yourself on your own machine.
#
# CODE_EXECUTION_MODE picks between them (auto, docker, subprocess, disabled). Nothing else in
# the app knows which one ran, so a hardened service can be added later as a third implementation.
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from typing import Any, Protocol
from dotenv import load_dotenv
from utils.helpers import StudyAssistantError, log_error, log_step
load_dotenv()
MODE_VAR = "CODE_EXECUTION_MODE"
IMAGE_VAR = "CODE_EXECUTION_IMAGE"
TIMEOUT_VAR = "CODE_EXECUTION_TIMEOUT"
MEMORY_VAR = "CODE_EXECUTION_MEMORY_MB"
AUTO = "auto"
DOCKER = "docker"
SUBPROCESS = "subprocess"
DISABLED = "disabled"
DEFAULT_IMAGE = "python:3.11-alpine"
DEFAULT_TIMEOUT = 10
DEFAULT_MEMORY_MB = 256
MAX_OUTPUT_BYTES = 64 * 1024
PYTHON = "python"
JAVASCRIPT = "javascript"
# Languages this build can actually execute, and what runs them.
LANGUAGE_COMMANDS = {
    PYTHON: [sys.executable, "-I", "-B", "main.py"],
    JAVASCRIPT: ["node", "main.js"],
}
LANGUAGE_FILES = {PYTHON: "main.py", JAVASCRIPT: "main.js"}
# Code execution is unavailable or misconfigured.
class SandboxError(StudyAssistantError):
    pass
# What happened when the code ran.
@dataclass(frozen=True)
class ExecutionResult:
    passed: int = 0
    total: int = 0
    cases: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""
    timed_out: bool = False
    memory_exceeded: bool = False
    runtime_ms: float = 0.0
    memory_kb: int = 0
    isolation: str = SUBPROCESS
    # True when every test passed and nothing blew up.
    @property
    def all_passed(self) -> bool:
        return self.total > 0 and self.passed == self.total and not self.error
    # The cases that did not pass, for feedback.
    @property
    def failures(self) -> list[dict[str, Any]]:
        return [case for case in self.cases if not case.get("passed")]
# Any execution backend.
class CodeRunner(Protocol):
    name: str
    def run(self, code: str, language: str, tests: list[dict[str, Any]], function_name: str) -> ExecutionResult: ...
# How long code may run.
def timeout_seconds() -> int:
    try:
        return max(1, min(60, int(os.getenv(TIMEOUT_VAR, "").strip() or DEFAULT_TIMEOUT)))
    except ValueError:
        return DEFAULT_TIMEOUT
# How much memory a container may use.
def memory_mb() -> int:
    try:
        return max(64, min(2048, int(os.getenv(MEMORY_VAR, "").strip() or DEFAULT_MEMORY_MB)))
    except ValueError:
        return DEFAULT_MEMORY_MB
# The harness that runs inside the sandbox: it imports nothing of ours, calls the student's
# function once per test case and prints one JSON line. Written to disk next to their code.
PYTHON_HARNESS = '''
import json, os, sys, time, traceback
# Isolated mode drops the script directory from sys.path, so put just this directory back.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
def main():
    with open("cases.json", "r", encoding="utf-8") as handle:
        cases = json.load(handle)
    results, passed = [], 0
    try:
        import main as solution
    except BaseException:
        print(json.dumps({"error": traceback.format_exc(limit=3), "cases": [], "passed": 0}))
        return
    target = getattr(solution, FUNCTION_NAME, None)
    if target is None:
        print(json.dumps({"error": "Your file does not define " + FUNCTION_NAME + "().", "cases": [], "passed": 0}))
        return
    for case in cases:
        started = time.perf_counter()
        record = {"input": case["input"], "expected": case["expected"], "passed": False}
        try:
            args = eval(case["input"], {"__builtins__": {}}, {})
            if not isinstance(args, tuple):
                args = (args,)
            expected = eval(case["expected"], {"__builtins__": {}}, {})
            actual = target(*args)
            record["actual"] = repr(actual)
            record["passed"] = actual == expected
        except BaseException:
            record["actual"] = None
            record["error"] = traceback.format_exc(limit=2)
        record["ms"] = round((time.perf_counter() - started) * 1000, 3)
        passed += 1 if record["passed"] else 0
        results.append(record)
    print(json.dumps({"error": "", "cases": results, "passed": passed}))
main()
'''
# A stand-in so the harness imports cleanly everywhere, including Windows where resource is absent.
RESOURCE_STUB = "pass\n"
# The JavaScript harness, same contract: read cases, call the function, print one JSON line.
JS_HARNESS = """
const fs = require('fs');
const cases = JSON.parse(fs.readFileSync('cases.json', 'utf8'));
let solution;
try { solution = require('./main.js'); }
catch (err) { console.log(JSON.stringify({error: String(err), cases: [], passed: 0})); process.exit(0); }
const target = solution[FUNCTION_NAME] || global[FUNCTION_NAME];
if (typeof target !== 'function') {
  console.log(JSON.stringify({error: 'Your file does not export ' + FUNCTION_NAME + '()', cases: [], passed: 0}));
  process.exit(0);
}
let passed = 0;
const results = cases.map((c) => {
  const started = process.hrtime.bigint();
  const record = {input: c.input, expected: c.expected, passed: false};
  try {
    let args = eval('(' + c.input + ')');
    if (!Array.isArray(args)) args = [args];
    const expected = eval('(' + c.expected + ')');
    const actual = target(...args);
    record.actual = JSON.stringify(actual);
    record.passed = JSON.stringify(actual) === JSON.stringify(expected);
  } catch (err) { record.error = String(err); }
  record.ms = Number(process.hrtime.bigint() - started) / 1e6;
  if (record.passed) passed += 1;
  return record;
});
console.log(JSON.stringify({error: '', cases: results, passed}));
"""
# Python tuple syntax is not JavaScript array syntax; translate the test literals.
def _js_literal(value: str) -> str:
    text = str(value).strip()
    if text.startswith("(") and text.endswith(")"):
        inner = text[1:-1].strip().rstrip(",")
        return f"[{inner}]"
    return text
# Lay out a working directory: the student's code, the harness and the test cases.
def _prepare(directory: str, code: str, language: str, tests: list[dict[str, Any]], function_name: str) -> None:
    filename = LANGUAGE_FILES[language]
    with open(os.path.join(directory, filename), "w", encoding="utf-8") as handle:
        handle.write(code)
    if language == PYTHON:
        harness = PYTHON_HARNESS.replace("FUNCTION_NAME", repr(function_name))
        cases = [{"input": test["input"], "expected": test["expected"]} for test in tests]
    else:
        harness = JS_HARNESS.replace("FUNCTION_NAME", json.dumps(function_name))
        cases = [
            {"input": _js_literal(test["input"]), "expected": _js_literal(test["expected"])}
            for test in tests
        ]
    harness_name = "harness.py" if language == PYTHON else "harness.js"
    with open(os.path.join(directory, harness_name), "w", encoding="utf-8") as handle:
        handle.write(harness)
    with open(os.path.join(directory, "cases.json"), "w", encoding="utf-8") as handle:
        json.dump(cases, handle)
# Read the harness's JSON line out of whatever the process printed.
def _parse_output(stdout: str, stderr: str, total: int, elapsed: float, isolation: str) -> ExecutionResult:
    line = ""
    for candidate in reversed(stdout.strip().splitlines()):
        if candidate.strip().startswith("{"):
            line = candidate
            break
    if not line:
        return ExecutionResult(
            passed=0, total=total, cases=[],
            error=(stderr or stdout or "The program produced no result.")[:2000],
            runtime_ms=elapsed, isolation=isolation,
        )
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return ExecutionResult(
            passed=0, total=total, error="The program produced unreadable output.",
            runtime_ms=elapsed, isolation=isolation,
        )
    return ExecutionResult(
        passed=int(payload.get("passed", 0)),
        total=total,
        cases=payload.get("cases", []),
        error=str(payload.get("error", ""))[:2000],
        runtime_ms=elapsed,
        isolation=isolation,
    )
# Runs code in a separate interpreter process. Process isolation only — see the module comment.
class SubprocessRunner:
    name = SUBPROCESS
    def __init__(self, timeout: int | None = None) -> None:
        self.timeout = timeout or timeout_seconds()
    # Execute the tests and collect the result.
    def run(self, code: str, language: str, tests: list[dict[str, Any]], function_name: str) -> ExecutionResult:
        if language not in LANGUAGE_COMMANDS:
            raise SandboxError(f"This server cannot run {language} code.")
        if language == JAVASCRIPT and shutil.which("node") is None:
            raise SandboxError("Node.js is not installed on this server, so JavaScript cannot run.")
        with tempfile.TemporaryDirectory(prefix="sa_code_") as directory:
            _prepare(directory, code, language, tests, function_name)
            command = list(LANGUAGE_COMMANDS[language])
            command[-1] = "harness.py" if language == PYTHON else "harness.js"
            # A minimal environment: no API keys, no user paths, no inherited configuration.
            environment = {
                "PATH": os.environ.get("PATH", ""),
                "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
                "PYTHONIOENCODING": "utf-8",
                "PYTHONDONTWRITEBYTECODE": "1",
                "HOME": directory,
                "TMPDIR": directory,
            }
            started = time.perf_counter()
            try:
                completed = subprocess.run(
                    command, cwd=directory, env=environment, capture_output=True, text=True,
                    timeout=self.timeout, check=False,
                )
            except subprocess.TimeoutExpired:
                return ExecutionResult(
                    passed=0, total=len(tests), timed_out=True,
                    error=f"Your code did not finish within {self.timeout} seconds.",
                    runtime_ms=self.timeout * 1000, isolation=self.name,
                )
            except OSError as error:
                log_error("Could not start the code runner")
                raise SandboxError(f"Could not run your code: {error}")
            elapsed = round((time.perf_counter() - started) * 1000, 2)
            return _parse_output(
                completed.stdout[:MAX_OUTPUT_BYTES], completed.stderr[:MAX_OUTPUT_BYTES],
                len(tests), elapsed, self.name,
            )
# Runs code in a throwaway container: no network, read-only root, memory and pid caps, non-root.
class DockerRunner:
    name = DOCKER
    def __init__(self, image: str = "", timeout: int | None = None) -> None:
        self.image = image or os.getenv(IMAGE_VAR, "").strip() or DEFAULT_IMAGE
        self.timeout = timeout or timeout_seconds()
    # Execute the tests inside a container.
    def run(self, code: str, language: str, tests: list[dict[str, Any]], function_name: str) -> ExecutionResult:
        if language != PYTHON:
            raise SandboxError(
                f"The sandbox image runs Python only. Configure {IMAGE_VAR} with an image that "
                f"includes {language} to run it here."
            )
        with tempfile.TemporaryDirectory(prefix="sa_code_") as directory:
            _prepare(directory, code, language, tests, function_name)
            command = [
                "docker", "run", "--rm",
                "--network", "none",
                "--memory", f"{memory_mb()}m",
                "--memory-swap", f"{memory_mb()}m",
                "--cpus", "0.5",
                "--pids-limit", "64",
                "--read-only",
                "--tmpfs", "/tmp:rw,size=16m",
                "--user", "65534:65534",
                "--workdir", "/work",
                "--volume", f"{directory}:/work:ro",
                "--env", "PYTHONDONTWRITEBYTECODE=1",
                self.image, "python", "-I", "-B", "/work/harness.py",
            ]
            started = time.perf_counter()
            try:
                completed = subprocess.run(
                    command, capture_output=True, text=True, timeout=self.timeout + 10, check=False
                )
            except subprocess.TimeoutExpired:
                return ExecutionResult(
                    passed=0, total=len(tests), timed_out=True,
                    error=f"Your code did not finish within {self.timeout} seconds.",
                    runtime_ms=self.timeout * 1000, isolation=self.name,
                )
            except OSError as error:
                raise SandboxError(f"The Docker sandbox could not start: {error}")
            elapsed = round((time.perf_counter() - started) * 1000, 2)
            result = _parse_output(
                completed.stdout[:MAX_OUTPUT_BYTES], completed.stderr[:MAX_OUTPUT_BYTES],
                len(tests), elapsed, self.name,
            )
            # Docker reports an out-of-memory kill as exit code 137.
            if completed.returncode == 137:
                return ExecutionResult(
                    passed=result.passed, total=len(tests), cases=result.cases,
                    memory_exceeded=True, error=f"Your code used more than {memory_mb()} MB.",
                    runtime_ms=elapsed, isolation=self.name,
                )
            return result
# True when a Docker daemon is actually reachable, not just when the CLI exists.
def docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        probe = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True, text=True, timeout=8, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return probe.returncode == 0
# The configured execution mode.
def configured_mode() -> str:
    mode = (os.getenv(MODE_VAR, "").strip() or AUTO).lower()
    return mode if mode in (AUTO, DOCKER, SUBPROCESS, DISABLED) else AUTO
# Pick the runner for this environment.
# 'auto' prefers Docker and falls back to a subprocess, which is weaker isolation and says so.
def select_runner() -> CodeRunner:
    mode = configured_mode()
    if mode == DISABLED:
        raise SandboxError(
            "Code execution is switched off on this server. Set CODE_EXECUTION_MODE to 'docker' "
            "to turn it on."
        )
    if mode == DOCKER:
        if not docker_available():
            raise SandboxError(
                "CODE_EXECUTION_MODE is 'docker' but no Docker daemon is reachable. Start Docker "
                "and try again."
            )
        return DockerRunner()
    if mode == SUBPROCESS:
        return SubprocessRunner()
    if docker_available():
        log_step("SANDBOX", "Running code in a Docker container")
        return DockerRunner()
    log_step("SANDBOX", "No Docker daemon; falling back to subprocess isolation")
    return SubprocessRunner()
# What the UI should tell the user about how their code will run.
def isolation_notice() -> tuple[str, str]:
    mode = configured_mode()
    if mode == DISABLED:
        return ("disabled", "Code execution is switched off on this server.")
    if mode in (DOCKER, AUTO) and docker_available():
        return (
            "docker",
            "Your code runs in a throwaway container with no network access, a read-only "
            "filesystem and memory and process limits.",
        )
    if mode == DOCKER:
        return ("unavailable", "Docker is configured but its daemon is not reachable.")
    return (
        "subprocess",
        "Your code runs in a separate, time-limited process on this machine. That stops runaway "
        "loops, but it is not a security sandbox — only run code you wrote yourself. Start Docker "
        "for proper isolation.",
    )
# The languages this server can execute right now.
def available_languages() -> list[str]:
    if configured_mode() == DISABLED:
        return []
    languages = [PYTHON]
    if shutil.which("node") is not None and not docker_available():
        languages.append(JAVASCRIPT)
    return languages
