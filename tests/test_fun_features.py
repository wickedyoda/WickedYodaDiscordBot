import importlib
import sys
from datetime import UTC, datetime
from pathlib import Path


def _load_bot_module(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "test-token")
    monkeypatch.setenv("GUILD_ID", "1234567890")
    monkeypatch.setenv("WEB_ENABLED", "false")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_USERNAME", "admin@example.com")
    monkeypatch.setenv("WEB_ADMIN_DEFAULT_PASSWORD", "StrongPass123!")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ACTION_DB_PATH", str(tmp_path / "data" / "actions.db"))
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("UPTIME_STATUS_PAGE_URL", "https://example.com/status/everything")
    monkeypatch.setenv("SHORTENER_BASE_URL", "https://l.twy4.us")
    sys.modules.pop("bot", None)
    module = importlib.import_module("bot")
    return importlib.reload(module)


def test_split_option_values_deduplicates_and_limits(tmp_path: Path, monkeypatch) -> None:
    bot = _load_bot_module(tmp_path, monkeypatch)

    options = bot.split_option_values("pizza, tacos | Pizza | burgers\nsalad", max_options=4)

    assert options == ["pizza", "tacos", "burgers", "salad"]


def test_parse_roll_expression_and_execute_roll(tmp_path: Path, monkeypatch) -> None:
    bot = _load_bot_module(tmp_path, monkeypatch)
    monkeypatch.setattr(bot, "secure_randint", lambda _low, _high: 4)

    count, sides, modifier = bot.parse_roll_expression("2d6+3")
    result = bot.execute_roll_expression("2d6+3")

    assert (count, sides, modifier) == (2, 6, 3)
    assert result["rolls"] == [4, 4]
    assert result["subtotal"] == 8
    assert result["total"] == 11


def test_parse_countdown_and_birthday_helpers(tmp_path: Path, monkeypatch) -> None:
    bot = _load_bot_module(tmp_path, monkeypatch)

    countdown = bot.parse_countdown_target("2026-12-31 23:00")
    month, day = bot.parse_month_day_input("2026-03-19")
    next_birthday = bot.next_birthday_occurrence(3, 19, now_dt=datetime(2026, 3, 1, tzinfo=UTC))

    assert countdown == datetime(2026, 12, 31, 23, 0, tzinfo=UTC)
    assert (month, day) == (3, 19)
    assert next_birthday == datetime(2026, 3, 19, tzinfo=UTC)
    assert bot.birthday_label(3, 19) == "March 19"


def test_action_store_birthdays_and_guess_game(tmp_path: Path, monkeypatch) -> None:
    bot = _load_bot_module(tmp_path, monkeypatch)
    store = bot.ActionStore(str(tmp_path / "fun.db"))

    store.save_birthday(1234567890, 42, "Tester#0001", 3, 19)
    birthday = store.get_birthday(1234567890, 42)
    assert birthday is not None
    assert birthday["month"] == 3
    assert birthday["day"] == 19

    listed = store.list_birthdays(1234567890)
    assert len(listed) == 1
    assert listed[0]["user_id"] == 42

    store.save_guess_game(1234567890, 77, 42, attempt_count=1)
    guess_game = store.get_guess_game(1234567890)
    assert guess_game is not None
    assert guess_game["target_number"] == 77
    assert guess_game["attempt_count"] == 1

    store.update_guess_game_attempts(1234567890, 3)
    updated_game = store.get_guess_game(1234567890)
    assert updated_game is not None
    assert updated_game["attempt_count"] == 3

    assert store.clear_guess_game(1234567890) is True
    assert store.get_guess_game(1234567890) is None
    assert store.delete_birthday(1234567890, 42) is True


def test_guild_spicy_settings_and_prompt_cache(tmp_path: Path, monkeypatch) -> None:
    bot = _load_bot_module(tmp_path, monkeypatch)
    store = bot.ActionStore(str(tmp_path / "spicy.db"))

    store.save_guild_settings(
        1234567890,
        bot_log_channel_id=None,
        spicy_prompts_enabled=True,
        spicy_prompts_channel_id=222,
    )
    settings = store.get_guild_settings(1234567890)
    assert settings["spicy_prompts_enabled"] == 1
    assert settings["spicy_prompts_channel_id"] == 222

    store.replace_spicy_prompt_catalog(
        {
            "repo_url": "https://github.com/wickedyoda/SpicyGameAndBookTokQuiz",
            "repo_branch": "main",
            "manifest_path": "manifests/index.json",
            "manifest_url": "https://raw.githubusercontent.com/wickedyoda/SpicyGameAndBookTokQuiz/main/manifests/index.json",
            "packs": [
                {
                    "pack_id": "spicy-core",
                    "pack_name": "Spicy Core",
                    "source_path": "packs/spicy-core.json",
                    "prompt_count": 1,
                }
            ],
            "prompts": [
                {
                    "pack_id": "spicy-core",
                    "prompt_id": "prompt_001",
                    "prompt_type": "prompt",
                    "category": "flirty",
                    "rating": "18+",
                    "text": "Describe your ideal late-night date in one sentence.",
                    "tags": ["adult", "text-only"],
                }
            ],
        }
    )
    prompt = store.get_random_spicy_prompt()
    assert prompt is not None
    assert prompt["pack_id"] == "spicy-core"
    assert prompt["prompt_id"] == "prompt_001"
    assert prompt["text"] == "Describe your ideal late-night date in one sentence."


def test_translation_store_and_settings(tmp_path: Path, monkeypatch) -> None:
    from app.translation import TranslationStore, get_lang_for_flag, parse_channel_ids_list

    # 1. Flag mapping test
    assert get_lang_for_flag("🇪🇸") == "es"
    assert get_lang_for_flag("🇫🇷") == "fr"
    assert get_lang_for_flag("🇯🇵") == "ja"
    assert get_lang_for_flag("🇬🇧") == "en"
    assert get_lang_for_flag("invalid") is None

    # 2. Channel IDs parser test
    assert parse_channel_ids_list([123, "456", "abc"]) == [123, 456]
    assert parse_channel_ids_list("123, 456, 789") == [123, 456, 789]
    assert parse_channel_ids_list(None) == []

    # 3. TranslationStore DB test
    store = TranslationStore(str(tmp_path / "translation.db"))
    default_settings = store.get_settings(999)
    assert default_settings["flag_translation_enabled"] == 0
    assert default_settings["flag_translation_mode"] == "reply"
    assert default_settings["context_menu_enabled"] == 1
    assert default_settings["channel_auto_translate_enabled"] == 0

    saved = store.save_settings(
        999,
        flag_translation_enabled=1,
        flag_translation_mode="ephemeral",
        context_menu_enabled=1,
        channel_auto_translate_enabled=1,
        channel_auto_translate_channel_ids=[1001, 1002],
        channel_auto_translate_target_lang="es",
    )
    assert saved["flag_translation_enabled"] == 1
    assert saved["flag_translation_mode"] == "ephemeral"
    assert saved["channel_auto_translate_enabled"] == 1
    assert saved["channel_auto_translate_channel_ids"] == [1001, 1002]
    assert saved["channel_auto_translate_target_lang"] == "es"

    loaded = store.get_settings(999)
    assert loaded["flag_translation_enabled"] == 1
    assert loaded["flag_translation_mode"] == "ephemeral"
    assert loaded["channel_auto_translate_channel_ids"] == [1001, 1002]
    assert loaded["channel_auto_translate_target_lang"] == "es"
