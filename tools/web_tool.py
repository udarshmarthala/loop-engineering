import httpx
from config import TASK_TIMEOUT_SECONDS


async def fetch_url(url: str, timeout: int = TASK_TIMEOUT_SECONDS) -> dict:
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
            response = await client.get(url)
            return {
                "content": response.text,
                "status_code": response.status_code,
                "success": response.is_success,
                "error": None,
            }
    except Exception as e:
        return {"content": "", "status_code": -1, "success": False, "error": str(e)}
