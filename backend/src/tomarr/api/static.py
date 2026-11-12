from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.responses import FileResponse
from starlette.exceptions import HTTPException

API_PREFIX = "api"
READ_METHODS = ("GET", "HEAD")
OTHER_METHODS = ("POST", "PUT", "PATCH", "DELETE", "OPTIONS")


def serve_build(app: FastAPI, build: Path) -> None:
    root = build.resolve()
    index = root / "index.html"

    # Every method is registered so a write to an unknown API path reaches the 404 below, not the
    # 405 Starlette sends when a route matches the path but not the method.
    @app.api_route("/{path:path}", methods=[*READ_METHODS, *OTHER_METHODS], include_in_schema=False)
    def serve(path: str, request: Request) -> FileResponse:
        if path == API_PREFIX or path.startswith(f"{API_PREFIX}/"):
            raise HTTPException(status.HTTP_404_NOT_FOUND)
        if request.method not in READ_METHODS:
            raise HTTPException(
                status.HTTP_405_METHOD_NOT_ALLOWED, headers={"Allow": ", ".join(READ_METHODS)}
            )
        # A client route such as /series/1 has no file behind it, so it gets index.html and the
        # router in the browser takes over.
        return FileResponse(_file_inside(root, path) or index)


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
