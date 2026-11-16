from __future__ import annotations

from datetime import UTC, datetime

from app.moderation_ext import (
    ModerationStore,
    attachment_violation,
    chunk_text,
    contains_invite,
    count_emoji,
    detect_spam,
    escalation_action,
    extract_urls,
    in_quiet_hours,
    match_regex_rules,
    neutralize_csv_cell,
    url_allowed,
)


def test_contains_invite_detects_common_forms():
    assert contains_invite("join discord.gg/abc123")
    assert contains_invite("https://discord.com/invite/xyz")
    assert not contains_invite("discord is a chat app")


def test_extract_urls_and_allowlist():
    urls = extract_urls("see https://example.com/a and http://sub.example.org/b")
    assert urls == ["https://example.com/a", "http://sub.example.org/b"]
    assert url_allowed("https://example.com/a", ["example.com"])
    assert url_allowed("https://sub.example.com/a", ["example.com"])
    assert not url_allowed("https://evil-example.com/a", ["example.com"])


def test_match_regex_rules_handles_invalid_patterns():
    rules = [{"pattern": "(", "reason": "bad"}, {"pattern": r"\bscam\b", "reason": "scam link"}]
    assert match_regex_rules("this is a scam", rules) == "scam link"
    assert match_regex_rules("clean text", rules) is None


def test_attachment_violation():
    blocked = ["exe", "ps1"]
    assert attachment_violation([{"filename": "tool.exe", "size": 10}], blocked, 25) == "blocked attachment type .exe"
    assert attachment_violation([{"filename": "big.zip", "size": 30 * 1024 * 1024}], blocked, 25) == "attachment exceeds 25 MB"
    assert attachment_violation([{"filename": "ok.png", "size": 1024}], blocked, 25) is None


def test_detect_spam_rules():
    settings = {
        "duplicate_threshold": 3,
        "mention_limit": 3,
        "emoji_limit": 3,
        "caps_ratio": 0.7,
    }
    assert (
        detect_spam(content="hello", recent_contents=["hello", "hello"], mention_count=0, emoji_count=0, settings=settings)
        == "repeated message"
    )
    assert detect_spam(content="hi", recent_contents=[], mention_count=5, emoji_count=0, settings=settings) == "mention spam (5 mentions)"
    assert detect_spam(content="hi", recent_contents=[], mention_count=0, emoji_count=5, settings=settings) == "emoji spam (5 emoji)"
    assert (
        detect_spam(content="THIS IS ALL SHOUTING", recent_contents=[], mention_count=0, emoji_count=0, settings=settings)
        == "excessive capitalisation"
    )
    assert detect_spam(content="normal message", recent_contents=[], mention_count=0, emoji_count=0, settings=settings) is None


def test_escalation_action_picks_highest_rung():
    ladder = [
        {"threshold": 2, "action": "timeout", "minutes": 10},
        {"threshold": 4, "action": "kick"},
        {"threshold": 6, "action": "ban"},
    ]
    assert escalation_action(1, ladder) is None
    assert escalation_action(2, ladder)["action"] == "timeout"
    assert escalation_action(5, ladder)["action"] == "kick"
    assert escalation_action(9, ladder)["action"] == "ban"


def test_in_quiet_hours_wraps_midnight():
    assert in_quiet_hours(datetime(2026, 1, 1, 23, tzinfo=UTC), 22, 7)
    assert in_quiet_hours(datetime(2026, 1, 1, 3, tzinfo=UTC), 22, 7)
    assert not in_quiet_hours(datetime(2026, 1, 1, 12, tzinfo=UTC), 22, 7)


def test_count_emoji_includes_custom_and_unicode():
    assert count_emoji("😀😀") == 2
    assert count_emoji("<:party:123456789>") == 1
    assert count_emoji("<a:dance:987654321>") == 1
    assert count_emoji("😀 <:party:123456789> <a:dance:987654321>") == 3
    assert count_emoji("plain text") == 0


def test_zero_mention_limit_disables_the_check():
    settings = {"duplicate_threshold": 3, "mention_limit": 0, "emoji_limit": 10, "caps_ratio": 0.7}
    assert detect_spam(content="hi", recent_contents=[], mention_count=20, emoji_count=0, settings=settings) is None


def test_chunk_text_respects_limit():
    text = "\n".join(f"line {index}" for index in range(500))
    chunks = chunk_text(text, limit=200)
    assert len(chunks) > 1
    assert all(len(chunk) <= 200 for chunk in chunks)
    assert "\n".join(chunks) == text


def test_neutralize_csv_cell_blocks_formulas():
    assert neutralize_csv_cell("=cmd|' /C calc'!A0").startswith("'")
    assert neutralize_csv_cell("+1").startswith("'")
    assert neutralize_csv_cell("-2").startswith("'")
    assert neutralize_csv_cell("@SUM(A1)").startswith("'")
    assert neutralize_csv_cell("normal") == "normal"
    assert neutralize_csv_cell(None) == ""


def test_store_cases_notes_warnings_reports(tmp_path):
    store = ModerationStore(str(tmp_path / "mod.db"))
    first = store.create_case(guild_id=1, action="warn", target_id=42, target_name="user", reason="spam")
    second = store.create_case(guild_id=1, action="ban", target_id=42, target_name="user", reason="repeat")
    assert (first, second) == (1, 2)
    assert store.get_case(1, 1)["action"] == "warn"
    assert len(store.list_cases(1, target_id=42)) == 2
    assert store.count_cases(1, 42, "warn") == 1
    assert store.update_case_reason(1, 1, "updated", "mod") is True
    assert store.get_case(1, 1)["reason"] == "updated"

    store.add_note(guild_id=1, target_id=42, author_id=7, author_name="mod", note="watch this user")
    assert store.list_notes(1, 42)[0]["note"] == "watch this user"

    store.add_warning(guild_id=1, user_id=42, moderator_id=7, moderator_name="mod", reason="spam", case_number=1)
    assert store.count_warnings(1, 42) == 1
    assert store.clear_warnings(1, 42) == 1
    assert store.count_warnings(1, 42) == 0

    report_id = store.create_report(
        guild_id=1,
        reporter_id=9,
        reporter_name="reporter",
        target_id=42,
        target_name="user",
        channel_id=5,
        message_id=6,
        message_excerpt="bad",
        reason="abuse",
    )
    assert store.list_reports(1)[0]["id"] == report_id
    assert store.get_report(1, report_id)["status"] == "open"
    assert store.resolve_report(1, report_id, actor="mod", resolution="handled") is True
    assert store.get_report(1, report_id)["status"] == "resolved"
    assert store.list_reports(1) == []


def test_store_appeals_and_shared_bans(tmp_path):
    store = ModerationStore(str(tmp_path / "mod.db"))
    appeal_id = store.create_appeal(guild_id=1, user_id=42, user_name="user", case_number=3, message="please")
    assert store.list_appeals(1)[0]["id"] == appeal_id
    assert store.get_appeal(1, appeal_id)["user_id"] == 42
    assert store.resolve_appeal(1, appeal_id, actor="mod", response="denied") is True
    assert store.list_appeals(1) == []

    store.add_shared_ban(42, reason="raid", added_by="mod")
    assert store.get_shared_ban(42)["reason"] == "raid"
    assert len(store.list_shared_bans()) == 1
    assert store.remove_shared_ban(42) is True
    assert store.get_shared_ban(42) is None


def test_store_automod_settings_roundtrip(tmp_path):
    store = ModerationStore(str(tmp_path / "mod.db"))
    defaults = store.get_automod_settings(1)
    assert defaults["enabled"] == 0
    assert defaults["mention_limit"] == 5

    saved = store.save_automod_settings(
        1,
        enabled=1,
        mention_limit=8,
        link_allowlist=["example.com"],
        regex_rules=[{"pattern": "scam", "reason": "scam"}],
        exempt_role_ids=[10, 11],
        escalation=[{"threshold": 3, "action": "timeout", "minutes": 15}],
    )
    assert saved["enabled"] == 1
    assert saved["mention_limit"] == 8
    assert saved["link_allowlist"] == ["example.com"]
    assert saved["exempt_role_ids"] == [10, 11]
    assert saved["escalation"][0]["action"] == "timeout"


def test_store_raid_and_lockdown(tmp_path):
    store = ModerationStore(str(tmp_path / "mod.db"))
    store.record_join(1, 100, 2.0)
    store.record_join(1, 101, 3.0)
    assert store.recent_join_count(1, 60) == 2

    store.set_lockdown(1, active=True, reason="raid", actor="mod", minutes=30)
    assert store.get_lockdown(1)["active"] == 1
    store.set_lockdown(1, active=False, reason="clear", actor="mod")
    assert store.get_lockdown(1)["active"] == 0
