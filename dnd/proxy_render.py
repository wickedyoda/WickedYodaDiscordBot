from __future__ import annotations

from typing import Optional


def render_proxy_payload(proxy: dict, content: str) -> tuple[str, str, str]:
    display_name = proxy.get("name", "Proxy")
    avatar_url = proxy.get("avatar_url", "")
    template = proxy.get("template", "{name}: {content}")
    rendered = template.replace("{name}", display_name).replace("{content}", content)
    return display_name, avatar_url, rendered
