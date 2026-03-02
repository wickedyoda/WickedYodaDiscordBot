import sqlite3
from pathlib import Path

from web_admin import create_app


def _bot_snapshot() -> dict:
    return {
        "bot_name": "Test Bot",
        "guild_id": 1234567890,
        "latency_ms": 42,
        "commands_synced": 6,
        "started_at": "2026-01-01T00:00:00+00:00",
    }


def test_healthz_route(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_PASSWORD", "TestPass123!")
    app = create_app(str(tmp_path / "actions.db"), _bot_snapshot)
    client = app.test_client()

    response = client.get("/healthz")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert "timestamp" in payload


def test_admin_redirects_to_login_when_not_authenticated(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_PASSWORD", "TestPass123!")
    app = create_app(str(tmp_path / "actions.db"), _bot_snapshot)
    client = app.test_client()

    response = client.get("/admin", follow_redirects=False)

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_login_and_dashboard_access(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_PASSWORD", "TestPass123!")
    app = create_app(str(tmp_path / "actions.db"), _bot_snapshot)
    client = app.test_client()

    response = client.post(
        "/login",
        data={"username": "admin@example.com", "password": "TestPass123!"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Latest Actions" in response.data


def test_actions_list_renders_existing_records(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_PASSWORD", "TestPass123!")
    db_path = tmp_path / "actions.db"

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                action TEXT NOT NULL,
                status TEXT NOT NULL,
                moderator TEXT,
                target TEXT,
                reason TEXT,
                guild TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO actions (created_at, action, status, moderator, target, reason, guild)
            VALUES ('2026-01-01 00:00:00', 'kick', 'success', 'mod', 'user', 'reason', 'guild')
            """
        )
        conn.commit()

    app = create_app(str(db_path), _bot_snapshot)
    client = app.test_client()
    client.post("/login", data={"username": "admin@example.com", "password": "TestPass123!"}, follow_redirects=True)

    response = client.get("/admin/actions")

    assert response.status_code == 200
    assert b"kick" in response.data


def test_youtube_subscription_add_and_render(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_PASSWORD", "TestPass123!")

    def channel_options() -> list[dict]:
        return [{"id": 9999, "name": "#alerts"}]

    def resolver(_url: str) -> dict:
        return {
            "source_url": "https://www.youtube.com/@example",
            "channel_id": "UC1234567890123456789012",
            "channel_title": "Example Channel",
            "last_video_id": "video123",
            "last_video_title": "Example Upload",
            "last_published_at": "2026-03-02T00:00:00+00:00",
        }

    app = create_app(
        str(tmp_path / "actions.db"),
        _bot_snapshot,
        get_notification_channels=channel_options,
        resolve_youtube_subscription=resolver,
    )
    client = app.test_client()
    client.post("/login", data={"username": "admin@example.com", "password": "TestPass123!"}, follow_redirects=True)

    response = client.post(
        "/admin/youtube/add",
        data={"youtube_url": "https://www.youtube.com/@example", "notify_channel_id": "9999"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"YouTube subscription saved." in response.data
    assert b"Example Channel" in response.data
    assert b"#alerts" in response.data


def test_settings_save_updates_env_file(tmp_path: Path, monkeypatch) -> None:
    env_file = tmp_path / "env.env"
    env_file.write_text("DISCORD_TOKEN=token123\nWEB_PORT=8080\n", encoding="utf-8")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_PASSWORD", "TestPass123!")
    monkeypatch.setenv("WEB_ENV_FILE", str(env_file))

    app = create_app(str(tmp_path / "actions.db"), _bot_snapshot)
    client = app.test_client()
    client.post("/login", data={"username": "admin@example.com", "password": "TestPass123!"}, follow_redirects=True)

    response = client.post(
        "/admin/settings/save",
        data={"WEB_PORT": "8000", "DISCORD_TOKEN": "********"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    saved = env_file.read_text(encoding="utf-8")
    assert "WEB_PORT=8000" in saved
    assert "DISCORD_TOKEN=token123" in saved


def test_logs_and_wiki_pages_render(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "wiki").mkdir()
    (tmp_path / "wiki" / "Command-Reference.md").write_text("# Commands\n", encoding="utf-8")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_PASSWORD", "TestPass123!")

    app = create_app(str(tmp_path / "actions.db"), _bot_snapshot)
    client = app.test_client()
    client.post("/login", data={"username": "admin@example.com", "password": "TestPass123!"}, follow_redirects=True)

    logs_response = client.get("/admin/logs")
    wiki_response = client.get("/admin/wiki")

    assert logs_response.status_code == 200
    assert b"Logs" in logs_response.data
    assert wiki_response.status_code == 200
    assert b"Command-Reference.md" in wiki_response.data
