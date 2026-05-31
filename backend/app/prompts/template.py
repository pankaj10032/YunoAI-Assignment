from __future__ import annotations

from hashlib import sha1
import re
from threading import Lock
from typing import Any


DEFAULT_CONTEXT_WINDOW = 8000
PLACEHOLDERS = ("user_context", "memory_summary", "guardrail_rules", "current_time")
_CACHE: dict[str, str] = {}
_LOCK = Lock()


def render_template(base_prompt: str, variables: dict[str, Any]) -> str:
    template = base_prompt or ""
    values = {name: _stringify(variables.get(name, "")) for name in PLACEHOLDERS}
    rendered = template
    for placeholder, value in values.items():
        rendered = rendered.replace(f"{{{{{placeholder}}}}}", value)

    rendered = _squash_blank_lines(rendered).strip()
    max_tokens = int(variables.get("context_window") or DEFAULT_CONTEXT_WINDOW)
    if _estimate_tokens(rendered) <= max_tokens:
        return rendered

    summarized = _summarize(rendered, max_tokens, values)
    return _squash_blank_lines(summarized).strip()


def cached_render(
    template_key: str,
    base_prompt: str,
    variables: dict[str, Any],
    version_key: str | None = None,
) -> str:
    cache_key = _cache_key(template_key, base_prompt, version_key, variables)
    with _LOCK:
        cached = _CACHE.get(cache_key)
    if cached is not None:
        return cached
    rendered = render_template(base_prompt, variables)
    with _LOCK:
        _CACHE[cache_key] = rendered
    return rendered


def invalidate_template_cache(template_key: str | None = None) -> None:
    with _LOCK:
        if template_key is None:
            _CACHE.clear()
            return
        for key in [key for key in _CACHE if key.startswith(f"{template_key}:")]:
            _CACHE.pop(key, None)


def preview_prompt(base_prompt: str, variables: dict[str, Any]) -> str:
    return render_template(base_prompt, variables)


def _cache_key(
    template_key: str,
    base_prompt: str,
    version_key: str | None,
    variables: dict[str, Any],
) -> str:
    digest = sha1()
    digest.update(base_prompt.encode("utf-8"))
    digest.update(str(version_key or "").encode("utf-8"))
    for name in PLACEHOLDERS:
        digest.update(_stringify(variables.get(name, "")).encode("utf-8"))
    return f"{template_key}:{digest.hexdigest()}"


def _summarize(rendered: str, max_tokens: int, values: dict[str, str]) -> str:
    head = rendered[: max(200, min(len(rendered), max_tokens * 4 // 3))]
    tail = rendered[-min(200, max(0, max_tokens * 2 // 5)) :] if len(rendered) > 300 else ""
    summary_bits = [
        "Prompt was truncated to fit the model context window.",
        f"User context: {values['user_context'][:240]}".strip(),
        f"Memory summary: {values['memory_summary'][:240]}".strip(),
        f"Guardrails: {values['guardrail_rules'][:240]}".strip(),
        f"Current time: {values['current_time']}".strip(),
        "Prompt excerpt:",
        head,
    ]
    if tail and tail != head:
        summary_bits.extend(["Tail excerpt:", tail])
    return "\n\n".join(bit for bit in summary_bits if bit)


def _estimate_tokens(text: str) -> int:
    return max(1, len(re.findall(r"\S+", text)))


def _squash_blank_lines(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text)


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return ", ".join(f"{key}={_stringify(item)}" for key, item in value.items())
    if isinstance(value, list):
        return ", ".join(_stringify(item) for item in value)
    return str(value)
