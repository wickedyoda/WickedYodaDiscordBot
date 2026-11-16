from __future__ import annotations

from webui.app import create_app


def test_moderation_web_routes_registered(tmp_path):
    app = create_app(str(tmp_path / "web.db"), lambda: {})
    rules = {rule.rule for rule in app.url_map.iter_rules()}
    assert "/admin/moderation" in rules
    assert "/admin/moderation/cases" in rules
    assert "/admin/moderation/cases/export" in rules
