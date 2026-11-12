from pathlib import Path

from fastapi import FastAPI, status
from fastapi.responses import FileResponse
from starlette.exceptions import HTTPException

API_PREFIX = "api"


def serve_build(app: FastAPI, build: Path) -> None:
    root = build.resolve()
    index = root / "index.html"

    # A client route such as /series/1 has no file behind it, so it gets index.html and the
    # router in the browser takes over.
    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    def serve(path: str) -> FileResponse:
        if path == API_PREFIX or path.startswith(f"{API_PREFIX}/"):
            raise HTTPException(status.HTTP_404_NOT_FOUND)
        file = _file_inside(root, path)
        return FileResponse(file or index)


def _file_inside(root: Path, path: str) -> Path | None:
    try:
        # Encoded slashes and dots reach the handler decoded, and an absolute path replaces the
        # root in the join. Resolving first and then checking the parent catches both, and
        # symlinks that leave the directory.
        candidate = (root / path).resolve()
    except ValueError:
        # A null byte in the path.
        return None
    return candidate if candidate.is_relative_to(root) and candidate.is_file() else None
