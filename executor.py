import anthropic
from schemas.task import Task, TaskResult
from tools.bash_tool import run_bash
from tools.file_tool import read_file, write_file
from tools.web_tool import fetch_url
from config import LLM_MODEL, TASK_TIMEOUT_SECONDS


client = anthropic.Anthropic()


async def run(task: Task, scratchpad: dict) -> TaskResult:
    try:
        if task.tool == "bash":
            command = task.inputs.get("command", "")
            res = await run_bash(command, timeout=TASK_TIMEOUT_SECONDS)
            output = res["stdout"] or res["stderr"]
            return TaskResult(
                task_id=task.id,
                output=output,
                success=res["success"],
                error=res["stderr"] if not res["success"] else None,
            )

        elif task.tool == "file":
            op = task.inputs.get("operation", "read")
            path = task.inputs.get("path", "")
            if op == "read":
                res = read_file(path)
                return TaskResult(
                    task_id=task.id,
                    output=res["content"],
                    success=res["success"],
                    error=res["error"],
                )
            elif op == "write":
                content = task.inputs.get("content", "")
                res = write_file(path, content)
                return TaskResult(
                    task_id=task.id,
                    output=f"Written to {path}" if res["success"] else "",
                    success=res["success"],
                    error=res["error"],
                    artifacts=[path] if res["success"] else [],
                )

        elif task.tool == "web":
            url = task.inputs.get("url", "")
            res = await fetch_url(url, timeout=TASK_TIMEOUT_SECONDS)
            return TaskResult(
                task_id=task.id,
                output=res["content"][:4000],
                success=res["success"],
                error=res["error"],
            )

        elif task.tool == "llm":
            prompt = task.inputs.get("prompt", task.description)
            context = task.inputs.get("context", "")
            full_prompt = f"{context}\n\n{prompt}" if context else prompt
            message = client.messages.create(
                model=LLM_MODEL,
                max_tokens=2048,
                messages=[{"role": "user", "content": full_prompt}],
            )
            output = message.content[0].text
            return TaskResult(task_id=task.id, output=output, success=True)

        else:
            return TaskResult(
                task_id=task.id, output="", success=False, error=f"Unknown tool: {task.tool}"
            )

    except Exception as e:
        return TaskResult(task_id=task.id, output="", success=False, error=str(e))
