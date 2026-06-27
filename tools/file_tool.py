from pathlib import Path


def read_file(path: str) -> dict:
    try:
        content = Path(path).read_text()
        return {"content": content, "success": True, "error": None}
    except Exception as e:
        return {"content": "", "success": False, "error": str(e)}


def write_file(path: str, content: str) -> dict:
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return {"success": True, "error": None}
    except Exception as e:
        return {"success": False, "error": str(e)}


def list_files(directory: str, pattern: str = "*") -> dict:
    try:
        files = [str(p) for p in Path(directory).rglob(pattern)]
        return {"files": files, "success": True, "error": None}
    except Exception as e:
        return {"files": [], "success": False, "error": str(e)}
