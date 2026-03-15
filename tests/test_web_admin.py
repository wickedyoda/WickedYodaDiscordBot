import io
import re
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


def _extract_csrf_token(response_body: bytes) -> str:
    html = response_body.decode("utf-8", errors="ignore")
    match = re.search(r'<meta name="csrf-token" content="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def _login(client) -> str:
    response = client.post(
        "/login",
        data={"username": "admin@example.com", "password": "TestPass123!"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    return _extract_csrf_token(response.data)


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


def test_coop_headers_omitted_for_untrusted_http_origin(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_PASSWORD", "TestPass123!")
    app = create_app(str(tmp_path / "actions.db"), _bot_snapshot)
    client = app.test_client()

    response = client.get("/healthz", base_url="http://docker2.tail99133.ts.net:8065")

    assert response.status_code == 200
    assert "Cross-Origin-Opener-Policy" not in response.headers
    assert "Cross-Origin-Resource-Policy" not in response.headers


def test_coop_headers_set_for_https_origin(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_PASSWORD", "TestPass123!")
    app = create_app(str(tmp_path / "actions.db"), _bot_snapshot)
    client = app.test_client()

    response = client.get("/healthz", base_url="https://docker2.tail99133.ts.net:8065")

    assert response.status_code == 200
    assert response.headers.get("Cross-Origin-Opener-Policy") == "same-origin"
    assert response.headers.get("Cross-Origin-Resource-Policy") == "same-origin"
    assert "Strict-Transport-Security" in response.headers


def test_coop_headers_set_for_forwarded_https_proto(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_PASSWORD", "TestPass123!")
    app = create_app(str(tmp_path / "actions.db"), _bot_snapshot)
    client = app.test_client()

    response = client.get(
        "/healthz",
        base_url="http://docker2.tail99133.ts.net:8065",
        headers={"X-Forwarded-Proto": "https"},
    )

    assert response.status_code == 200
    assert response.headers.get("Cross-Origin-Opener-Policy") == "same-origin"
    assert response.headers.get("Cross-Origin-Resource-Policy") == "same-origin"
    assert "Strict-Transport-Security" in response.headers


def test_admin_redirects_to_login_when_not_authenticated(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_PASSWORD", "TestPass123!")
    app = create_app(str(tmp_path / "actions.db"), _bot_snapshot)
    client = app.test_client()

    response = client.get("/admin", follow_redirects=False)

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_login_and_home_access(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_PASSWORD", "TestPass123!")
    app = create_app(str(tmp_path / "actions.db"), _bot_snapshot)
    client = app.test_client()
    response = client.post("/login", data={"username": "admin@example.com", "password": "TestPass123!"}, follow_redirects=True)

    assert response.status_code == 200
    assert b"Control Center" in response.data


def test_login_allows_forwarded_host_origin_match(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_PASSWORD", "TestPass123!")
    app = create_app(str(tmp_path / "actions.db"), _bot_snapshot)
    client = app.test_client()

    response = client.post(
        "/login",
        data={"username": "admin@example.com", "password": "TestPass123!"},
        headers={
            "Origin": "http://docker2.tail99133.ts.net:8065",
            "X-Forwarded-Host": "docker2.tail99133.ts.net:8065",
        },
        base_url="http://127.0.0.1:8080",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/admin/home" in response.headers["Location"]


def test_login_not_blocked_by_same_origin_policy(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_PASSWORD", "TestPass123!")
    app = create_app(str(tmp_path / "actions.db"), _bot_snapshot)
    client = app.test_client()

    response = client.post(
        "/login",
        data={"username": "admin@example.com", "password": "TestPass123!"},
        headers={"Origin": "http://not-the-same-origin.example"},
        base_url="http://127.0.0.1:8080",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/admin/home" in response.headers["Location"]


def test_select_guild_not_blocked_by_same_origin_policy(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_PASSWORD", "TestPass123!")
    monkeypatch.setenv("GUILD_ID", "123456789012345678")
    app = create_app(str(tmp_path / "actions.db"), _bot_snapshot)
    client = app.test_client()
    csrf_token = _login(client)

    response = client.post(
        "/admin/select-guild",
        data={
            "guild_id": "123456789012345678",
            "next_endpoint": "home",
        },
        headers={
            "Origin": "http://not-the-same-origin.example",
            "X-CSRF-Token": csrf_token,
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/admin/home" in response.headers["Location"]


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
            VALUES ('2026-01-01 00:00:00', 'kick', 'success', 'mod', 'user', 'reason', '1234567890')
            """
        )
        conn.commit()

    app = create_app(str(db_path), _bot_snapshot)
    client = app.test_client()
    _login(client)

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
    csrf_token = _login(client)

    response = client.post(
        "/admin/youtube/add",
        data={"youtube_url": "https://www.youtube.com/@example", "notify_channel_id": "9999"},
        headers={"X-CSRF-Token": csrf_token},
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
    csrf_token = _login(client)

    response = client.post(
        "/admin/settings/save",
        data={"WEB_PORT": "8000", "DISCORD_TOKEN": "********"},
        headers={"X-CSRF-Token": csrf_token, "Origin": "http://not-the-same-origin.example"},
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
    _login(client)

    logs_response = client.get("/admin/logs")
    wiki_redirect = client.get("/admin/wiki", follow_redirects=False)
    wiki_response = client.get("/admin/wiki", follow_redirects=True)

    assert logs_response.status_code == 200
    assert b"Logs" in logs_response.data
    assert wiki_redirect.status_code == 302
    assert wiki_redirect.headers["Location"] == "/admin/documentation"
    assert wiki_response.status_code == 200
    assert b"Documentation" in wiki_response.data
    assert b"Command-Reference.md" in wiki_response.data


def test_guilds_page_renders_managed_servers(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_PASSWORD", "TestPass123!")

    def get_managed_guilds() -> list[dict]:
        return [
            {"id": 111111111111111111, "name": "Alpha Guild", "member_count": 42, "is_primary": True},
            {"id": 222222222222222222, "name": "Beta Guild", "member_count": 13, "is_primary": False},
        ]

    app = create_app(
        str(tmp_path / "actions.db"),
        _bot_snapshot,
        get_managed_guilds=get_managed_guilds,
    )
    client = app.test_client()
    _login(client)

    response = client.get("/admin/guilds")

    assert response.status_code == 200
    assert b"Discord Servers" in response.data
    assert b"Alpha Guild" in response.data
    assert b"Beta Guild" in response.data


def test_documentation_page_renders_selected_wiki_doc(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "wiki").mkdir()
    (tmp_path / "wiki" / "Home.md").write_text("# Home\nLanding page\n", encoding="utf-8")
    (tmp_path / "wiki" / "Command-Reference.md").write_text("# Commands\nPing and logs\n", encoding="utf-8")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_PASSWORD", "TestPass123!")

    app = create_app(str(tmp_path / "actions.db"), _bot_snapshot)
    client = app.test_client()
    _login(client)

    index_response = client.get("/admin/documentation", follow_redirects=False)
    page_response = client.get("/admin/documentation/Command-Reference")

    assert index_response.status_code == 302
    assert "/admin/documentation/Home" in index_response.headers["Location"]
    assert page_response.status_code == 200
    assert b"Commands" in page_response.data
    assert b"Ping and logs" in page_response.data


def test_observability_and_bot_profile_pages_render(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_PASSWORD", "TestPass123!")

    def get_bot_profile() -> dict:
        return {
            "ok": True,
            "id": 123,
            "name": "WickedYodaBot",
            "global_name": "WickedYodaBot",
            "avatar_url": "",
            "guild_name": "Test Guild",
            "server_nickname": "",
        }

    def update_bot_profile(payload: dict, _actor: str) -> dict:
        return get_bot_profile() | {"message": "updated", **payload}

    def update_bot_avatar(_payload: bytes, _filename: str, _actor: str) -> dict:
        return get_bot_profile() | {"avatar_url": "https://example.com/avatar.png", "message": "avatar updated"}

    app = create_app(
        str(tmp_path / "actions.db"),
        _bot_snapshot,
        get_bot_profile=get_bot_profile,
        update_bot_profile=update_bot_profile,
        update_bot_avatar=update_bot_avatar,
    )
    client = app.test_client()

    csrf_token = _login(client)
    observability_response = client.get("/admin/observability")
    profile_response = client.get("/admin/bot-profile")
    avatar_response = client.post(
        "/admin/bot-profile",
        data={
            "action": "avatar",
            "avatar_file": (io.BytesIO(b"fakepngbytes"), "avatar.png"),
        },
        headers={"X-CSRF-Token": csrf_token},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    restart_response = client.post("/admin/restart", headers={"X-CSRF-Token": csrf_token}, follow_redirects=True)

    assert observability_response.status_code == 200
    assert b"Observability" in observability_response.data
    assert profile_response.status_code == 200
    assert b"Bot Profile" in profile_response.data
    assert avatar_response.status_code == 200
    assert b"avatar updated" in avatar_response.data
    assert restart_response.status_code == 200


def test_command_permissions_and_tag_pages_render(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_PASSWORD", "TestPass123!")

    def get_command_permissions() -> dict:
        return {
            "ok": True,
            "commands": [
                {
                    "key": "ping",
                    "label": "/ping",
                    "description": "Health check",
                    "default_policy_label": "Public (all members)",
                    "mode": "default",
                    "role_ids": [],
                }
            ],
        }

    def save_command_permissions(_payload: dict, _email: str) -> dict:
        return get_command_permissions() | {"message": "updated"}

    def get_tag_responses() -> dict:
        return {"ok": True, "mapping": {"!support": "Need help?"}}

    def save_tag_responses(mapping: dict, _email: str) -> dict:
        return {"ok": True, "mapping": mapping, "message": "updated"}

    app = create_app(
        str(tmp_path / "actions.db"),
        _bot_snapshot,
        get_command_permissions=get_command_permissions,
        save_command_permissions=save_command_permissions,
        get_tag_responses=get_tag_responses,
        save_tag_responses=save_tag_responses,
    )
    client = app.test_client()
    _login(client)

    permissions_response = client.get("/admin/command-permissions")
    tags_response = client.get("/admin/tag-responses")

    assert permissions_response.status_code == 200
    assert b"Command Permissions" in permissions_response.data
    assert tags_response.status_code == 200
    assert b"Tag Responses" in tags_response.data


def test_home_dashboard_and_status_are_distinct(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_PASSWORD", "TestPass123!")
    app = create_app(str(tmp_path / "actions.db"), _bot_snapshot)
    client = app.test_client()
    _login(client)

    home_response = client.get("/admin/home")
    dashboard_response = client.get("/admin")
    status_response = client.get("/admin/status")

    assert home_response.status_code == 200
    assert b"Control Center" in home_response.data
    assert dashboard_response.status_code == 200
    assert b"Latest Actions" in dashboard_response.data
    assert status_response.status_code == 200
    assert b"Service Status" in status_response.data
    assert b"Status Log Tail" in status_response.data


def test_logs_fall_back_to_db_directory_when_configured_log_dir_invalid(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_PASSWORD", "TestPass123!")
    invalid_log_dir = tmp_path / "not-a-directory"
    invalid_log_dir.write_text("x", encoding="utf-8")
    monkeypatch.setenv("LOG_DIR", str(invalid_log_dir))
    (tmp_path / "bot.log").write_text("fallback bot log line\n", encoding="utf-8")

    app = create_app(str(tmp_path / "actions.db"), _bot_snapshot)
    client = app.test_client()
    _login(client)

    response = client.get("/admin/logs?log=bot.log")

    assert response.status_code == 200
    assert b"fallback bot log line" in response.data


def test_command_permissions_save_not_blocked_by_same_origin_policy(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_PASSWORD", "TestPass123!")

    def get_command_permissions(_guild_id: int) -> dict:
        return {
            "ok": True,
            "commands": [
                {
                    "key": "ping",
                    "label": "/ping",
                    "description": "Health check",
                    "default_policy_label": "Public (all members)",
                    "mode": "default",
                    "role_ids": [],
                }
            ],
        }

    def save_command_permissions(_payload: dict, _actor: str, guild_id: int) -> dict:
        return get_command_permissions(guild_id) | {"message": "Command permissions updated.", "ok": True}

    app = create_app(
        str(tmp_path / "actions.db"),
        _bot_snapshot,
        get_command_permissions=get_command_permissions,
        save_command_permissions=save_command_permissions,
    )
    client = app.test_client()
    csrf_token = _login(client)

    response = client.post(
        "/admin/command-permissions",
        data={"command_key": "ping", "mode__ping": "public", "role_ids_text__ping": ""},
        headers={"X-CSRF-Token": csrf_token, "Origin": "http://not-the-same-origin.example"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Command permissions updated." in response.data


def test_tag_responses_save_not_blocked_by_same_origin_policy(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_PASSWORD", "TestPass123!")

    def get_tag_responses(_guild_id: int) -> dict:
        return {"ok": True, "mapping": {"hello": "world"}}

    def save_tag_responses(mapping: dict, _actor: str, _guild_id: int) -> dict:
        return {"ok": True, "mapping": mapping, "message": "Tag responses updated."}

    app = create_app(
        str(tmp_path / "actions.db"),
        _bot_snapshot,
        get_tag_responses=get_tag_responses,
        save_tag_responses=save_tag_responses,
    )
    client = app.test_client()
    csrf_token = _login(client)

    response = client.post(
        "/admin/tag-responses",
        data={"tag_json": '{"hello": "updated"}'},
        headers={"X-CSRF-Token": csrf_token, "Origin": "http://not-the-same-origin.example"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Tag responses updated." in response.data


def test_guild_settings_save_not_blocked_by_same_origin_policy(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_PASSWORD", "TestPass123!")

    def get_discord_catalog(_guild_id: int) -> dict:
        return {"ok": True, "channels": [{"id": 111222333444555666, "name": "#bot-logs"}]}

    def get_guild_settings(_guild_id: int) -> dict:
        return {"ok": True, "bot_log_channel_id": ""}

    def save_guild_settings(_payload: dict, _actor: str, _guild_id: int) -> dict:
        return {"ok": True, "bot_log_channel_id": 111222333444555666, "message": "Guild settings updated."}

    app = create_app(
        str(tmp_path / "actions.db"),
        _bot_snapshot,
        get_discord_catalog=get_discord_catalog,
        get_guild_settings=get_guild_settings,
        save_guild_settings=save_guild_settings,
    )
    client = app.test_client()
    csrf_token = _login(client)

    response = client.post(
        "/admin/guild-settings",
        data={"bot_log_channel_id": "111222333444555666"},
        headers={"X-CSRF-Token": csrf_token, "Origin": "http://not-the-same-origin.example"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Guild settings updated." in response.data
