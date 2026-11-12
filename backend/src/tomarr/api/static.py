from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.responses import FileResponse
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException
from starlette.routing import Match
from starlette.types import Scope

API_PREFIX = "api"
ASSETS_PREFIX = "assets"
READ_METHODS = ("GET", "HEAD")
OTHER_METHODS = ("POST", "PUT", "PATCH", "DELETE", "OPTIONS")


class _BuildRoute(APIRoute):
    def matches(self, scope: Scope) -> tuple[Match, Scope]:
        match, child_scope = super().matches(scope)
        # The catch-all never claims an /api path. Its full match would beat the partial match of
        # a real route and turn that route's 405 into a 404, so the router is left to send the 405,
        # or its own 404 when nothing matches.
        if match is not Match.NONE and _is_under(child_scope["path_params"]["path"], API_PREFIX):
            return Match.NONE, {}
        return match, child_scope


def serve_build(app: FastAPI, build: Path) -> None:
    root = build.resolve()
    index = root / "index.html"

    def serve(path: str, request: Request) -> FileResponse:
        if request.method not in READ_METHODS:
            raise HTTPException(
                status.HTTP_405_METHOD_NOT_ALLOWED, headers={"Allow": ", ".join(READ_METHODS)}
            )
        file = _file_inside(root, path)
        if file is not None:
            return FileResponse(file)
        # A browser holding an old index.html must not get HTML back for a module script.
        if _is_under(path, ASSETS_PREFIX):
            raise HTTPException(status.HTTP_404_NOT_FOUND)
        # A client route such as /series/1 has no file behind it, so it gets index.html and the
        # router in the browser takes over.
        return FileResponse(index)

    app.router.add_api_route(
        "/{path:path}",
        serve,
        methods=[*READ_METHODS, *OTHER_METHODS],
        include_in_schema=False,
        route_class_override=_BuildRoute,
    )


def _is_under(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(f"{prefix}/")


def _file_inside(root: Path, path: str) -> Path | None:
    try:
        # Encoded slashes and dots reach the handler decoded, and an absolute path replaces the
        # root in the join. Resolving first and then checking the parent catches both, and
        # symlinks that leave the directory.
        candidate = (root / path).resolve()
        found = candidate.is_relative_to(root) and candidate.is_file()
    except (ValueError, OSError):
        # A null byte in the path, or a name too long for the file system, which is_file raises
        # instead of returning False.
        return None
    return candidate if found else None
