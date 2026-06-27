# Loop Engineering

Autonomous agent that plans, executes, evaluates, and self-corrects across multi-step tasks.

## Quickstart

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-...

# Run a goal
python loop.py --goal "Fix all failing tests in src/"

# Run an example
python examples/self_healing_code.py
```

## Architecture

```
Planner → Executor → Evaluator → [ok: done | retry: refine+loop | fail: raise]
```

Every loop is bounded by `MAX_LOOP_ITERATIONS`. Low-confidence evaluations trigger a human-in-the-loop gate.

## Running Tests

```bash
pytest tests/ -v
```

## Config

Edit `config.py` to change model, timeouts, retry limits, or confidence threshold.
