# Loop Engineering Agent — CLAUDE.md

## Project Overview

Loop Engineering agent that can autonomously plan, execute, evaluate, and self-correct across multi-step tasks. Inspired by the principle: **agents don't just call tools once — they loop until the goal is provably met.**

---

## Architecture

```
User Goal
   │
   ▼
┌─────────────┐
│   Planner   │  ← Decompose goal into subtasks
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Executor   │  ← Run tool/subtask
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Evaluator  │  ← Did subtask succeed? Is goal met?
└──────┬──────┘
       │
   ┌───┴────┐
   │        │
  YES       NO
   │        │
   ▼        ▼
 Done    Reflect → re-plan → loop
```

---

## Loop Termination Contract

Every loop MUST have exactly one of:
1. **Success condition** — evaluator confirms goal met
2. **Failure condition** — max iterations hit OR unrecoverable error
3. **Human-in-loop gate** — confidence below threshold → pause, ask

No infinite loops. No silent failures.

---

## Core Modules

### 1. Planner (`planner.py`)
- Input: user goal string
- Output: `TaskList` — ordered subtasks with expected outputs
- Use structured output (JSON schema)
- Re-plan allowed after evaluator feedback

### 2. Executor (`executor.py`)
- Input: single `Task` from planner
- Output: `TaskResult` — stdout, exit_code, artifacts, error
- Wraps: bash, code interpreter, file ops, API calls
- Timeout per task: configurable (default 60s)

### 3. Evaluator (`evaluator.py`)
- Input: `Task` + `TaskResult`
- Output: `EvalResult` — `{status: ok|retry|fail, reason, suggestion}`
- Uses LLM call with rubric OR deterministic check (test assertions, exit code)
- Max retries per task: 3

### 4. Memory (`memory.py`)
- Short-term: full trace of current loop (plan → exec → eval per step)
- Long-term (optional): vector store for past runs / learnings
- Scratchpad: shared dict injected into every executor call

### 5. Loop Controller (`loop.py`)
- Orchestrates planner → executor → evaluator
- Manages retry logic, re-planning, termination
- Emits structured events: `PLAN`, `EXEC`, `EVAL`, `RETRY`, `DONE`, `FAIL`

---

## File Structure

```
loop-engineering/
├── CLAUDE.md              ← this file
├── README.md
├── loop.py                ← main controller
├── planner.py
├── executor.py
├── evaluator.py
├── memory.py
├── tools/
│   ├── bash_tool.py
│   ├── file_tool.py
│   └── web_tool.py
├── schemas/
│   ├── task.py            ← pydantic models
│   └── eval_result.py
├── tests/
│   ├── test_loop.py
│   └── test_evaluator.py
├── examples/
│   ├── fix_failing_tests.py
│   ├── research_and_report.py
│   └── self_healing_code.py
├── config.py
└── requirements.txt
```

---

## Key Data Schemas

```python
# schemas/task.py
class Task(BaseModel):
    id: str
    description: str
    expected_output: str
    tool: Literal["bash", "file", "web", "llm"]
    inputs: dict
    max_retries: int = 3

class TaskResult(BaseModel):
    task_id: str
    output: str
    success: bool
    error: Optional[str]
    artifacts: list[str] = []

class EvalResult(BaseModel):
    task_id: str
    status: Literal["ok", "retry", "fail"]
    reason: str
    suggestion: Optional[str]  # fed back into re-plan
```

---

## Loop Controller Logic

```python
# loop.py (pseudocode)
async def run(goal: str, max_iterations: int = 20):
    memory = Memory()
    tasks = await planner.plan(goal)
    iteration = 0

    for task in tasks:
        retries = 0
        while retries <= task.max_retries:
            iteration += 1
            if iteration > max_iterations:
                raise LoopLimitExceeded(f"Hit {max_iterations} iterations")

            result = await executor.run(task, memory.scratchpad)
            eval = await evaluator.evaluate(task, result)
            memory.add(task, result, eval)

            if eval.status == "ok":
                break
            elif eval.status == "retry":
                task = await planner.refine(task, eval.suggestion)
                retries += 1
            else:  # fail
                raise TaskFailed(task.id, eval.reason)

    return memory.full_trace()
```

---

## LLM Integration

- Model: `claude-sonnet-4-6` (via Anthropic SDK or Claude Code)
- Planner + Evaluator = LLM calls with structured output
- Executor tool calls = deterministic (no LLM hallucination in execution layer)
- System prompts: stored in `prompts/` directory, versioned

### Planner Prompt Template
```
You are a planning agent. Given a user goal, decompose it into ordered, atomic subtasks.
Each subtask must have: description, expected_output, tool (bash/file/web/llm), inputs.
Respond ONLY in valid JSON matching TaskList schema.
Goal: {goal}
Memory: {memory_summary}
```

### Evaluator Prompt Template
```
You are an evaluation agent. Given a task and its result, determine if the task succeeded.
Task: {task}
Result: {result}
Return JSON: {status: ok|retry|fail, reason, suggestion}
```

---

## Config

```python
# config.py
MAX_LOOP_ITERATIONS = 20
MAX_TASK_RETRIES = 3
TASK_TIMEOUT_SECONDS = 60
LLM_MODEL = "claude-sonnet-4-6"
CONFIDENCE_THRESHOLD = 0.8   # below = human-in-loop gate
ENABLE_LONG_TERM_MEMORY = False
LOG_LEVEL = "INFO"
```

---

## Example Use Cases

| Example | Loop Pattern |
|---------|-------------|
| Self-Healing Codebase | run tests → find failures → patch → re-run → loop until green |
| Research & Report | search → read → summarize → identify gaps → search again → compile |
| Data Pipeline Fix | run pipeline → detect error → diagnose → fix config → retry |
| Code Review Bot | read PR → check criteria → comment → wait for fix → re-review |

---

## Observability

Every loop emits structured JSON logs:

```json
{
  "event": "EVAL",
  "iteration": 3,
  "task_id": "fix_test_auth",
  "status": "retry",
  "reason": "test still fails — wrong mock path",
  "suggestion": "mock at module level not function level"
}
```

Plug into: stdout, file, or LangSmith / Langfuse for trace UI.

---

## Development Commands

```bash
# Run a goal
python loop.py --goal "Fix all failing tests in src/"

# Run with debug trace
python loop.py --goal "..." --log-level DEBUG

# Run example
python examples/self_healing_code.py

# Run tests
pytest tests/

# Lint
ruff check . && mypy .
```

---

## Loop Engineering Principles (guiding decisions)

1. **Loops over chains** — retry/re-plan beats linear pipeline
2. **Evaluator is first-class** — not an afterthought; determines if loop continues
3. **Deterministic executor** — LLM plans and judges, tools execute exactly
4. **Trace everything** — every iteration logged, diff-able
5. **Fail loudly** — no silent task skip; every failure surface up
6. **Human gate** — confidence threshold triggers pause, not silent failure
7. **Bounded always** — max_iterations enforced at controller level

---

## Related Projects (yours)

- `self-healing-codebase-agent` — specialization of this loop (test → patch loop)
- `open-seed` — behavior observation can feed goal extraction into this loop

---

## TODO

- [ ] Implement planner.py with structured output
- [ ] Implement evaluator.py with LLM rubric + deterministic fallback
- [ ] Build bash_tool.py with timeout + sandboxing
- [ ] Add confidence scoring to evaluator
- [ ] Human-in-loop gate (pause + prompt when confidence < threshold)
- [ ] Long-term memory via ChromaDB or Qdrant
- [ ] Web UI for trace visualization (React + SSE stream)
- [ ] Example: research_and_report.py
- [ ] Example: data_pipeline_fix.py