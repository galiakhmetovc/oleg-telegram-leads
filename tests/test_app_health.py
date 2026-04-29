from fastapi.testclient import TestClient

from pur_leads.web.app import create_app


def test_health_returns_ok(tmp_path):
    client = TestClient(
        create_app(
            database_path=tmp_path / "test.db",
            bootstrap_admin_password_file=tmp_path / "bootstrap-admin-password.txt",
        )
    )

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
