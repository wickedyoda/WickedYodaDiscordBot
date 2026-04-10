import io
import re
import sqlite3
import zipfile
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from webui import _ensure_spicy_prompt_tables, create_app


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
    return _login_as(client, "admin@example.com", "TestPass123!")


def _login_as(client, username: str, password: str) -> str:
    response = client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=True,
    )
    assert response.status_code == 200
    return _extract_csrf_token(response.data)


def _add_user(client, csrf_token: str, *, email: str, password: str, is_admin: bool, display_name: str = ""):
    return client.post(
        "/admin/users/add",
        data={
            "email": email,
            "password": password,
            "confirm_password": password,
            "role": "admin" if is_admin else "read-only",
            "display_name": display_name,
        },
        headers={"X-CSRF-Token": csrf_token},
        follow_redirects=True,
    )


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


def test_account_profile_update_changes_email_and_names(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_PASSWORD", "TestPass123!")
    db_path = tmp_path / "actions.db"
    app = create_app(str(db_path), _bot_snapshot)
    client = app.test_client()
    csrf_token = _login(client)

    response = client.post(
        "/admin/account",
        data={
            "action": "profile",
            "email": "owner@example.com",
            "first_name": "Wicked",
            "last_name": "Yoda",
            "current_password": "TestPass123!",
        },
        headers={"X-CSRF-Token": csrf_token},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Profile updated." in response.data
    assert b'value="Wicked"' in response.data
    assert b'value="Yoda"' in response.data
    assert b'value="owner@example.com"' in response.data

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT email, first_name, last_name FROM web_users WHERE email = ?",
            ("owner@example.com",),
        ).fetchone()

    assert row == ("owner@example.com", "Wicked", "Yoda")


def test_account_password_update_allows_login_with_new_password(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_PASSWORD", "TestPass123!")
    app = create_app(str(tmp_path / "actions.db"), _bot_snapshot)
    client = app.test_client()
    csrf_token = _login(client)

    response = client.post(
        "/admin/account",
        data={
            "action": "password",
            "current_password": "TestPass123!",
            "new_password": "UpdatedPass123!",
            "confirm_new_password": "UpdatedPass123!",
        },
        headers={"X-CSRF-Token": csrf_token},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Password updated." in response.data

    client.get("/logout", follow_redirects=True)
    login_response = client.post(
        "/login",
        data={"username": "admin@example.com", "password": "UpdatedPass123!"},
        follow_redirects=True,
    )

    assert login_response.status_code == 200
    assert b"Control Center" in login_response.data


def test_existing_admin_user_ignores_weak_default_password_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_PASSWORD", "StrongPass123!")
    db_path = tmp_path / "actions.db"
    app = create_app(str(db_path), _bot_snapshot)
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_PASSWORD", "short")

    app = create_app(str(db_path), _bot_snapshot)
    client = app.test_client()

    response = client.post(
        "/login",
        data={"username": "admin@example.com", "password": "StrongPass123!"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Control Center" in response.data


def test_new_install_rejects_weak_default_password_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_PASSWORD", "short")

    with pytest.raises(RuntimeError, match="WEB_ADMIN_DEFAULT_PASSWORD does not meet policy"):
        create_app(str(tmp_path / "actions.db"), _bot_snapshot)


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

    def community_resolver(_url: str) -> dict:
        return {
            "last_community_post_id": "Ugkxyz123",
            "last_community_post_title": "Example community update",
            "last_community_published_at": "2026-03-03T00:00:00+00:00",
        }

    app = create_app(
        str(tmp_path / "actions.db"),
        _bot_snapshot,
        get_notification_channels=channel_options,
        resolve_youtube_subscription=resolver,
        resolve_youtube_community_seed=community_resolver,
    )
    client = app.test_client()
    csrf_token = _login(client)

    response = client.post(
        "/admin/youtube/add",
        data={
            "youtube_url": "https://www.youtube.com/@example",
            "notify_channel_id": "9999",
            "poll_interval_seconds": "3600",
            "include_uploads": "1",
            "include_community_posts": "1",
        },
        headers={"X-CSRF-Token": csrf_token},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"YouTube subscription saved." in response.data
    assert b"Example Channel" in response.data
    assert b"#alerts" in response.data
    assert b"1 hour" in response.data
    assert b"Uploads + Posts" in response.data


def test_reddit_feed_add_and_render(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_PASSWORD", "TestPass123!")

    def channel_options() -> list[dict]:
        return [{"id": 9999, "name": "#alerts"}]

    app = create_app(
        str(tmp_path / "actions.db"),
        _bot_snapshot,
        get_notification_channels=channel_options,
    )
    client = app.test_client()
    csrf_token = _login(client)

    response = client.post(
        "/admin/reddit/add",
        data={
            "reddit_source": "r/python",
            "notify_channel_id": "9999",
            "poll_interval_seconds": "600",
        },
        headers={"X-CSRF-Token": csrf_token},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Reddit feed saved." in response.data
    assert b"r/python" in response.data
    assert b"#alerts" in response.data
    assert b"10 minutes" in response.data


def test_wordpress_feed_add_and_render(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_PASSWORD", "TestPass123!")

    def channel_options() -> list[dict]:
        return [{"id": 9999, "name": "#announcements"}]

    def wordpress_resolver(_url: str) -> dict:
        return {
            "site_url": "https://wickedyoda.com",
            "feed_url": "https://wickedyoda.com/feed/",
            "site_title": "WickedYoda",
            "last_post_id": "post-123",
            "last_post_title": "New Release Notes",
            "last_post_url": "https://wickedyoda.com/new-release-notes",
            "last_published_at": "2026-03-17T00:00:00+00:00",
        }

    app = create_app(
        str(tmp_path / "actions.db"),
        _bot_snapshot,
        get_notification_channels=channel_options,
        resolve_wordpress_feed=wordpress_resolver,
    )
    client = app.test_client()
    csrf_token = _login(client)

    response = client.post(
        "/admin/wordpress/add",
        data={
            "wordpress_site_url": "wickedyoda.com",
            "notify_channel_id": "9999",
            "poll_interval_seconds": "1800",
        },
        headers={"X-CSRF-Token": csrf_token},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"WordPress feed saved." in response.data
    assert b"WickedYoda" in response.data
    assert b"#announcements" in response.data
    assert b"30 minutes" in response.data
    assert b"New Release Notes" in response.data


def test_linkedin_feed_add_and_render(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_PASSWORD", "TestPass123!")

    def channel_options() -> list[dict]:
        return [{"id": 9999, "name": "#announcements"}]

    def linkedin_resolver(_url: str) -> dict:
        return {
            "profile_url": "https://www.linkedin.com/in/wickedyoda",
            "activity_url": "https://www.linkedin.com/in/wickedyoda/recent-activity/all",
            "profile_label": "WickedYoda",
            "last_post_id": "1234567890",
            "last_post_title": "Shipping a new update",
            "last_post_url": "https://www.linkedin.com/feed/update/urn:li:activity:1234567890",
            "last_published_at": "2026-03-17T00:00:00+00:00",
        }

    app = create_app(
        str(tmp_path / "actions.db"),
        _bot_snapshot,
        get_notification_channels=channel_options,
        resolve_linkedin_feed=linkedin_resolver,
    )
    client = app.test_client()
    csrf_token = _login(client)

    response = client.post(
        "/admin/linkedin/add",
        data={
            "linkedin_profile_url": "https://www.linkedin.com/in/wickedyoda",
            "notify_channel_id": "9999",
            "poll_interval_seconds": "900",
        },
        headers={"X-CSRF-Token": csrf_token},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"LinkedIn feed saved." in response.data
    assert b"WickedYoda" in response.data
    assert b"#announcements" in response.data
    assert b"15 minutes" in response.data
    assert b"Shipping a new update" in response.data


def test_spicy_prompts_refresh_and_render(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_PASSWORD", "TestPass123!")
    monkeypatch.setenv("SPICY_PROMPTS_ENABLED", "true")
    monkeypatch.setenv("SPICY_PROMPTS_REPO_URL", "https://github.com/wickedyoda/SpicyGameAndBookTokQuiz")
    monkeypatch.setenv("SPICY_PROMPTS_REPO_BRANCH", "main")
    monkeypatch.setenv("SPICY_PROMPTS_MANIFEST_PATH", "manifests/index.json")

    db_path = tmp_path / "actions.db"

    def refresh_callback(_actor_email: str) -> dict:
        _ensure_spicy_prompt_tables(str(db_path))
        with sqlite3.connect(db_path) as conn:
            now = "2026-03-19 12:00:00"
            conn.execute("DELETE FROM spicy_prompt_entries")
            conn.execute("DELETE FROM spicy_prompt_packs")
            conn.execute("DELETE FROM spicy_prompt_sync_state")
            conn.execute(
                """
                INSERT INTO spicy_prompt_packs (pack_id, pack_name, source_path, prompt_count, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                ("spicy-core", "Spicy Core", "packs/spicy-core.json", 1, now),
            )
            conn.execute(
                """
                INSERT INTO spicy_prompt_entries (
                    pack_id, prompt_id, prompt_type, category, rating, text, tags_json, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "spicy-core",
                    "truth_001",
                    "truth",
                    "flirty",
                    "18+",
                    "What is the boldest message you have ever wanted to send someone?",
                    '["adult","text-only"]',
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO spicy_prompt_sync_state (
                    state_id, repo_url, repo_branch, manifest_path, manifest_url,
                    last_refresh_at, last_success_at, last_error, pack_count, prompt_count
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    1,
                    "https://github.com/wickedyoda/SpicyGameAndBookTokQuiz",
                    "main",
                    "manifests/index.json",
                    "https://raw.githubusercontent.com/wickedyoda/SpicyGameAndBookTokQuiz/main/manifests/index.json",
                    now,
                    now,
                    "",
                    1,
                    1,
                ),
            )
            conn.commit()
        return {"ok": True, "message": "Refreshed Spicy Prompts: 1 packs, 1 prompts."}

    app = create_app(
        str(db_path),
        _bot_snapshot,
        refresh_spicy_prompts=refresh_callback,
    )
    client = app.test_client()
    csrf_token = _login(client)

    response = client.post(
        "/admin/spicy-prompts/refresh",
        headers={"X-CSRF-Token": csrf_token},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Refreshed Spicy Prompts: 1 packs, 1 prompts." in response.data
    assert b"Spicy Core" in response.data
    assert b"What is the boldest message you have ever wanted to send someone?" in response.data
    assert b"SpicyGameAndBookTokQuiz" in response.data


def test_spicy_prompts_settings_require_nsfw_channel(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_PASSWORD", "TestPass123!")

    def get_discord_catalog(_guild_id: int) -> dict:
        return {
            "ok": True,
            "guild": {"id": 1234567890, "name": "Guild"},
            "channels": [
                {"id": 111, "name": "#general", "nsfw": False},
                {"id": 222, "name": "#spicy", "nsfw": True},
            ],
            "roles": [],
        }

    def get_guild_settings(_guild_id: int) -> dict:
        return {
            "ok": True,
            "guild_id": 1234567890,
            "bot_log_channel_id": None,
            "spicy_prompts_enabled": 0,
            "spicy_prompts_channel_id": None,
        }

    app = create_app(
        str(tmp_path / "actions.db"),
        _bot_snapshot,
        get_discord_catalog=get_discord_catalog,
        get_guild_settings=get_guild_settings,
    )
    client = app.test_client()
    csrf_token = _login(client)

    response = client.post(
        "/admin/spicy-prompts/settings",
        data={"spicy_prompts_enabled": "1", "spicy_prompts_channel_id": "111"},
        headers={"X-CSRF-Token": csrf_token},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Spicy Prompts must use an age-restricted Discord channel." in response.data


def test_spicy_prompts_settings_save_uses_guild_settings_callback(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_PASSWORD", "TestPass123!")
    saved_payloads: list[dict] = []

    def get_discord_catalog(_guild_id: int) -> dict:
        return {
            "ok": True,
            "guild": {"id": 1234567890, "name": "Guild"},
            "channels": [
                {"id": 222, "name": "#spicy", "nsfw": True},
            ],
            "roles": [],
        }

    def get_guild_settings(_guild_id: int) -> dict:
        return {
            "ok": True,
            "guild_id": 1234567890,
            "bot_log_channel_id": None,
            "spicy_prompts_enabled": 0,
            "spicy_prompts_channel_id": None,
        }

    def save_guild_settings(payload: dict, _actor: str, _guild_id: int) -> dict:
        saved_payloads.append(payload)
        return {
            "ok": True,
            "guild_id": 1234567890,
            "bot_log_channel_id": None,
            "spicy_prompts_enabled": 1,
            "spicy_prompts_channel_id": 222,
            "message": "Spicy Prompts settings updated.",
        }

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
        "/admin/spicy-prompts/settings",
        data={"spicy_prompts_enabled": "1", "spicy_prompts_channel_id": "222"},
        headers={"X-CSRF-Token": csrf_token},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Spicy Prompts settings updated." in response.data
    assert saved_payloads
    assert saved_payloads[0]["spicy_prompts_enabled"] == "1"
    assert saved_payloads[0]["spicy_prompts_channel_id"] == "222"


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


def test_admin_can_leave_guild_from_guilds_page(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_PASSWORD", "TestPass123!")

    def get_managed_guilds() -> list[dict]:
        return [
            {"id": 111111111111111111, "name": "Alpha Guild", "member_count": 42, "is_primary": True},
            {"id": 222222222222222222, "name": "Beta Guild", "member_count": 13, "is_primary": False},
        ]

    leave_calls: list[tuple[str, int]] = []

    def leave_guild(actor: str, guild_id: int) -> dict:
        leave_calls.append((actor, guild_id))
        return {"ok": True, "message": "Left guild Beta Guild.", "guild_id": guild_id}

    app = create_app(
        str(tmp_path / "actions.db"),
        _bot_snapshot,
        get_managed_guilds=get_managed_guilds,
        leave_guild=leave_guild,
    )
    client = app.test_client()
    csrf_token = _login(client)

    response = client.post(
        "/admin/guilds/leave",
        data={"guild_id": "222222222222222222"},
        headers={"X-CSRF-Token": csrf_token},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Left guild Beta Guild." in response.data
    assert leave_calls == [("admin@example.com", 222222222222222222)]


def test_read_only_cannot_leave_guild(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_PASSWORD", "TestPass123!")
    app = create_app(str(tmp_path / "actions.db"), _bot_snapshot)
    client = app.test_client()
    admin_csrf = _login(client)

    add_response = _add_user(
        client,
        admin_csrf,
        email="viewer@example.com",
        password="ViewerPass123!",
        is_admin=False,
        display_name="Viewer",
    )
    assert add_response.status_code == 200

    client.get("/logout", follow_redirects=True)
    viewer_csrf = _login_as(client, "viewer@example.com", "ViewerPass123!")

    response = client.post(
        "/admin/guilds/leave",
        data={"guild_id": "111111111111111111"},
        headers={"X-CSRF-Token": viewer_csrf},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/admin" in response.headers["Location"]


def test_member_activity_page_renders_tables(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_PASSWORD", "TestPass123!")

    def get_member_activity(_guild_id: int, role_id: int | None = None) -> dict:
        return {
            "ok": True,
            "top_limit": 20,
            "selected_role_id": role_id or 0,
            "windows": [
                {
                    "key": "7d",
                    "label": "Last 7 Days",
                    "members": [
                        {
                            "rank": 1,
                            "user_id": 123,
                            "display_name": "Member One",
                            "username": "member1",
                            "message_count": 42,
                            "active_days": 5,
                            "last_message_at": "2026-03-18T00:00:00+00:00",
                        }
                    ],
                }
            ],
        }

    def get_discord_catalog(_guild_id: int) -> dict:
        return {"ok": True, "roles": [{"id": 555, "name": "Community"}], "channels": []}

    app = create_app(
        str(tmp_path / "actions.db"),
        _bot_snapshot,
        get_discord_catalog=get_discord_catalog,
        get_member_activity=get_member_activity,
    )
    client = app.test_client()
    _login(client)

    response = client.get("/admin/member-activity?role_id=555")

    assert response.status_code == 200
    assert b"Member Activity" in response.data
    assert b"Last 7 Days" in response.data
    assert b"Member One" in response.data
    assert b"Community" in response.data


def test_member_activity_export_downloads_zip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_PASSWORD", "TestPass123!")

    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("summary.json", '{"ok":true}')

    def export_member_activity(_guild_id: int, role_id: int | None = None) -> dict:
        assert role_id == 555
        return {
            "ok": True,
            "filename": "member_activity_test.zip",
            "content_type": "application/zip",
            "data": archive_buffer.getvalue(),
        }

    app = create_app(
        str(tmp_path / "actions.db"),
        _bot_snapshot,
        export_member_activity=export_member_activity,
    )
    client = app.test_client()
    _login(client)

    response = client.get("/admin/member-activity/export?role_id=555")

    assert response.status_code == 200
    assert response.mimetype == "application/zip"
    assert "member_activity_test.zip" in response.headers.get("Content-Disposition", "")


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


def test_account_can_update_own_email_name_and_password(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_PASSWORD", "TestPass123!")
    app = create_app(str(tmp_path / "actions.db"), _bot_snapshot)
    client = app.test_client()
    csrf_token = _login(client)

    response = client.post(
        "/admin/account",
        data={
            "display_name": "Admin Prime",
            "email": "admin2@example.com",
            "current_password": "TestPass123!",
            "new_password": "NewPass1234!",
            "confirm_new_password": "NewPass1234!",
        },
        headers={"X-CSRF-Token": csrf_token},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Account updated." in response.data
    assert b"Admin Prime" in response.data
    assert b"admin2@example.com" in response.data

    client.get("/logout")
    relogin_response = client.post(
        "/login",
        data={"username": "admin2@example.com", "password": "NewPass1234!"},
        follow_redirects=True,
    )

    assert relogin_response.status_code == 200
    assert b"Control Center" in relogin_response.data


def test_admin_can_update_other_user_email_name_and_password(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_PASSWORD", "TestPass123!")
    app = create_app(str(tmp_path / "actions.db"), _bot_snapshot)
    client = app.test_client()
    csrf_token = _login(client)

    add_response = _add_user(
        client,
        csrf_token,
        email="viewer@example.com",
        password="ViewerPass123!",
        is_admin=False,
        display_name="Viewer",
    )

    assert add_response.status_code == 200
    assert b"User saved." in add_response.data

    update_response = client.post(
        "/admin/users/update",
        data={
            "current_email": "viewer@example.com",
            "display_name": "Updated Viewer",
            "email": "viewer2@example.com",
            "new_password": "ViewerReset123!",
            "confirm_new_password": "ViewerReset123!",
            "admin_current_password": "TestPass123!",
            "role": "read-only",
        },
        headers={"X-CSRF-Token": csrf_token},
        follow_redirects=True,
    )

    assert update_response.status_code == 200
    assert b"User updated." in update_response.data
    assert b"Updated Viewer" in update_response.data
    assert b"viewer2@example.com" in update_response.data

    client.get("/logout")
    relogin_response = client.post(
        "/login",
        data={"username": "viewer2@example.com", "password": "ViewerReset123!"},
        follow_redirects=True,
    )

    assert relogin_response.status_code == 200
    assert b"Control Center" in relogin_response.data


def test_admin_cannot_make_self_read_only(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_PASSWORD", "TestPass123!")
    app = create_app(str(tmp_path / "actions.db"), _bot_snapshot)
    client = app.test_client()
    csrf_token = _login(client)

    response = client.post(
        "/admin/users/update",
        data={
            "current_email": "admin@example.com",
            "display_name": "Admin",
            "email": "admin@example.com",
            "is_admin": "0",
        },
        headers={"X-CSRF-Token": csrf_token},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"You cannot make your own account read-only." in response.data


def test_read_only_user_can_view_portal_but_cannot_modify_it(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_PASSWORD", "TestPass123!")
    monkeypatch.setenv("GUILD_ID", "123456789012345678")

    def get_discord_catalog(_guild_id: int) -> dict:
        return {
            "ok": True,
            "channels": [{"id": 111222333444555666, "name": "#bot-logs"}],
            "roles": [{"id": 777888999000111222, "name": "Moderators"}],
        }

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

    def get_tag_responses(_guild_id: int) -> dict:
        return {"ok": True, "mapping": {"hello": "world"}}

    def save_tag_responses(mapping: dict, _actor: str, _guild_id: int) -> dict:
        return {"ok": True, "mapping": mapping, "message": "Tag responses updated."}

    def get_guild_settings(_guild_id: int) -> dict:
        return {"ok": True, "bot_log_channel_id": ""}

    def save_guild_settings(_payload: dict, _actor: str, _guild_id: int) -> dict:
        return {"ok": True, "bot_log_channel_id": 111222333444555666, "message": "Guild settings updated."}

    def get_bot_profile(_guild_id: int) -> dict:
        return {
            "ok": True,
            "id": 123,
            "name": "WickedYodaBot",
            "global_name": "WickedYodaBot",
            "avatar_url": "",
            "guild_name": "Test Guild",
            "server_nickname": "",
        }

    app = create_app(
        str(tmp_path / "actions.db"),
        _bot_snapshot,
        get_discord_catalog=get_discord_catalog,
        get_command_permissions=get_command_permissions,
        save_command_permissions=save_command_permissions,
        get_tag_responses=get_tag_responses,
        save_tag_responses=save_tag_responses,
        get_guild_settings=get_guild_settings,
        save_guild_settings=save_guild_settings,
        get_bot_profile=get_bot_profile,
    )
    client = app.test_client()
    admin_csrf = _login(client)
    add_response = _add_user(
        client,
        admin_csrf,
        email="readonly@example.com",
        password="Readonly123!",
        is_admin=False,
        display_name="Read Only",
    )

    assert add_response.status_code == 200
    assert b"User saved." in add_response.data

    client.get("/logout")
    readonly_csrf = _login_as(client, "readonly@example.com", "Readonly123!")

    for path in (
        "/admin/users",
        "/admin/command-permissions",
        "/admin/tag-responses",
        "/admin/guild-settings",
        "/admin/settings",
        "/admin/bot-profile",
    ):
        response = client.get(path)
        assert response.status_code == 200

    users_response = client.get("/admin/users")
    assert b"Read-only account" in users_response.data
    assert b"disabled" in users_response.data

    select_response = client.post(
        "/admin/select-guild",
        data={"guild_id": "123456789012345678", "next_endpoint": "users"},
        headers={"X-CSRF-Token": readonly_csrf},
        follow_redirects=False,
    )
    assert select_response.status_code == 302
    assert "/admin/users" in select_response.headers["Location"]

    settings_response = client.post(
        "/admin/settings/save",
        data={"WEB_PORT": "8001"},
        headers={"X-CSRF-Token": readonly_csrf},
        follow_redirects=True,
    )
    command_response = client.post(
        "/admin/command-permissions",
        data={"command_key": "ping", "mode__ping": "public", "role_ids_text__ping": ""},
        headers={"X-CSRF-Token": readonly_csrf},
        follow_redirects=True,
    )

    assert settings_response.status_code == 200
    assert b"Read-only accounts can view this page but cannot make changes." in settings_response.data
    assert command_response.status_code == 200
    assert b"Read-only accounts can view this page but cannot make changes." in command_response.data


def test_login_upgrades_legacy_password_hash(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_PASSWORD", "TestPass123!")
    db_path = tmp_path / "actions.db"
    app = create_app(str(db_path), _bot_snapshot)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE web_users SET password_hash = ? WHERE email = ?",
            (generate_password_hash("TestPass123!", method="pbkdf2:sha256"), "admin@example.com"),
        )
        conn.commit()

    client = app.test_client()
    response = client.post(
        "/login",
        data={"username": "admin@example.com", "password": "TestPass123!"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    with sqlite3.connect(db_path) as conn:
        upgraded_hash = conn.execute(
            "SELECT password_hash FROM web_users WHERE email = ?",
            ("admin@example.com",),
        ).fetchone()[0]
    assert upgraded_hash.startswith("scrypt:")


def test_password_rotation_forces_account_update(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_PASSWORD", "TestPass123!")
    db_path = tmp_path / "actions.db"
    app = create_app(str(db_path), _bot_snapshot)

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE web_users SET password_changed_at = '2025-01-01 00:00:00' WHERE email = ?",
            ("admin@example.com",),
        )
        conn.commit()

    client = app.test_client()
    login_response = client.post(
        "/login",
        data={"username": "admin@example.com", "password": "TestPass123!"},
        follow_redirects=True,
    )

    assert login_response.status_code == 200
    assert b"older than 90 days" in login_response.data
    assert b"Account" in login_response.data

    csrf_token = _extract_csrf_token(login_response.data)
    blocked_response = client.post(
        "/admin/account",
        data={
            "display_name": "Admin",
            "email": "admin@example.com",
            "current_password": "TestPass123!",
            "new_password": "",
            "confirm_new_password": "",
        },
        headers={"X-CSRF-Token": csrf_token},
        follow_redirects=True,
    )

    assert blocked_response.status_code == 200
    assert b"Password rotation is required every 90 days" in blocked_response.data

    updated_response = client.post(
        "/admin/account",
        data={
            "display_name": "Admin",
            "email": "admin@example.com",
            "current_password": "TestPass123!",
            "new_password": "UpdatedPass123!",
            "confirm_new_password": "UpdatedPass123!",
        },
        headers={"X-CSRF-Token": csrf_token},
        follow_redirects=True,
    )

    assert updated_response.status_code == 200
    assert b"Account updated." in updated_response.data


def test_users_add_rejects_weak_password(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_PASSWORD", "TestPass123!")
    app = create_app(str(tmp_path / "actions.db"), _bot_snapshot)
    client = app.test_client()
    csrf_token = _login(client)

    response = _add_user(
        client,
        csrf_token,
        email="weak@example.com",
        password="weak",
        is_admin=False,
        display_name="Weak",
    )

    assert response.status_code == 200
    assert b"Password must be at least 6 characters." in response.data
