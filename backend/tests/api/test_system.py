from importlib.metadata import version

import httpx2
from fastapi.testclient import TestClient

from tomarr.app import create_app


def test_status_returns_installed_version() -> None:
    response = TestClient(create_app()).get("/api/v1/system/status")

    assert response.status_code == 200
    assert response.json() == {"version": version("tomarr")}


async def test_status_returns_installed_version_over_async_client() -> None:
    transport = httpx2.ASGITransport(app=create_app())
    async with httpx2.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/system/status")

    assert response.status_code == 200
    assert response.json() == {"version": version("tomarr")}


def test_status_is_in_openapi_with_system_status_schema() -> None:
    operation = create_app().openapi()["paths"]["/api/v1/system/status"]["get"]

    schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert schema == {"$ref": "#/components/schemas/SystemStatus"}
