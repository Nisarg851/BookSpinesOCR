"""
Hosted vision-language spine reader.

Provider: Cursor Cloud Agents API (https://api.cursor.com/v1/agents).
We POST the spine crop as a base64 image on a no-repo cloud agent and poll
the run until it finishes. This avoids the Cursor Python SDK local bridge,
which crashes on Windows (WinError 10038 — select() on a pipe).

Swap providers by changing `_call_provider` — `read_spine()` stays public.

Model default: composer-2.5 (multimodal). Plan usage; cost logged as $0 when
token meters aren't returned.

API key: CURSOR_API_KEY from the environment (or repo-root `.env`).
Never hardcode secrets.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from django.conf import settings

Status = Literal["ok", "unreadable", "timeout", "api_error", "missing_key"]

CURSOR_API_BASE = "https://api.cursor.com/v1"

# Cursor usage is typically plan-included; log $0 unless we have token meters.
INPUT_USD_PER_1M = 0.0
OUTPUT_USD_PER_1M = 0.0

SPINE_PROMPT = """You are reading text off a single book spine photo.
Return ONLY strict JSON with this exact shape (no markdown, no extra keys):
{"title":"...","author":"...","confidence_note":"..."}

Rules:
- title: the book title as printed on the spine. Empty string if unreadable.
- author: the author name as printed. Empty string if missing/unreadable.
- confidence_note: one short sentence about legibility (e.g. "clear", "blurry", "rotated").
- Do NOT invent a catalog match, ISBN, or publisher beyond what helps you read title/author.
- If the spine is sideways, mentally rotate and still return upright title/author text.
- Do not use tools. Do not edit files. Reply with the JSON only.
"""


@dataclass
class SpineRead:
    title: str
    author: str
    raw_text: str
    status: Status
    elapsed_ms: int
    estimated_cost_usd: float
    confidence_note: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0


def _load_repo_dotenv() -> None:
    """Load KEY=VALUE lines from repo-root .env into os.environ (no override)."""
    env_path = Path(settings.BASE_DIR).parent / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _api_key() -> str | None:
    _load_repo_dotenv()
    key = os.environ.get(settings.VLM_API_KEY_ENV, "").strip()
    return key or None


def _estimate_cost(prompt_tokens: int, completion_tokens: int) -> float:
    return (
        prompt_tokens * INPUT_USD_PER_1M + completion_tokens * OUTPUT_USD_PER_1M
    ) / 1_000_000


def _strip_fences(text: str) -> str:
    text = text.strip()
    fence = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", text, re.IGNORECASE)
    if fence:
        return fence.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def _parse_spine_json(raw: str) -> tuple[str, str, str] | None:
    """Return (title, author, confidence_note) or None on parse failure."""
    try:
        data = json.loads(_strip_fences(raw))
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    title = str(data.get("title") or "").strip()
    author = str(data.get("author") or "").strip()
    note = str(data.get("confidence_note") or "").strip()
    return title, author, note


def _basic_auth_header(api_key: str) -> str:
    token = base64.b64encode(f"{api_key}:".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def _cursor_request(
    method: str,
    path: str,
    api_key: str,
    body: dict[str, Any] | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{CURSOR_API_BASE}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": _basic_auth_header(api_key),
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Cursor API HTTP {exc.code}: {detail[:500]}") from exc
    except urllib.error.URLError as exc:
        raise TimeoutError(str(exc)) from exc

    if not raw:
        return {}
    return json.loads(raw)


def _call_cursor(image_path: Path, api_key: str) -> tuple[str, int, int]:
    """
    Cloud Agents REST adapter (no local SDK bridge).
    Returns (raw_content, prompt_tokens, completion_tokens).
    """
    mime, _ = mimetypes.guess_type(str(image_path))
    if mime not in {"image/jpeg", "image/png", "image/gif", "image/webp"}:
        mime = "image/jpeg"
    image_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")

    created = _cursor_request(
        "POST",
        "/agents",
        api_key,
        body={
            "prompt": {
                "text": SPINE_PROMPT,
                "images": [{"data": image_b64, "mimeType": mime}],
            },
            "model": {"id": settings.VLM_MODEL},
            "name": "shelfie-spine-read",
        },
        timeout=60.0,
    )
    agent = created.get("agent") or {}
    run = created.get("run") or {}
    agent_id = agent.get("id")
    run_id = run.get("id")
    if not agent_id or not run_id:
        raise RuntimeError(f"Unexpected create response: {created!r}")

    deadline = time.monotonic() + float(settings.VLM_TIMEOUT_S)
    last: dict[str, Any] = run
    while time.monotonic() < deadline:
        status = (last.get("status") or "").upper()
        if status in {"FINISHED", "ERROR", "CANCELLED", "EXPIRED"}:
            break
        time.sleep(1.5)
        last = _cursor_request(
            "GET",
            f"/agents/{agent_id}/runs/{run_id}",
            api_key,
            timeout=30.0,
        )
    else:
        raise TimeoutError(
            f"Cursor run {run_id} did not finish within {settings.VLM_TIMEOUT_S}s"
        )

    status = (last.get("status") or "").upper()
    raw = (last.get("result") or "").strip()
    if status != "FINISHED":
        raise RuntimeError(f"Cursor run status={status} result={raw[:300]!r}")

    # Best-effort cleanup so spine reads don't pile up in the dashboard.
    try:
        _cursor_request("POST", f"/agents/{agent_id}/archive", api_key, body={})
    except Exception:
        pass

    return raw, 0, 0


def _call_provider(image_path: Path, api_key: str) -> tuple[str, int, int]:
    """Single swap point for hosted providers."""
    return _call_cursor(image_path, api_key)


def read_spine(image_path: str | Path) -> SpineRead:
    """
    Read title/author from one spine crop. Never raises to the caller.

    Timing: each call reports elapsed_ms; callers that process a whole
    ShelfPhoto should SUM those into ShelfPhoto.vlm_ms (per-image README total).
    """
    path = Path(image_path)
    if not path.is_file():
        return SpineRead(
            title="",
            author="",
            raw_text="",
            status="unreadable",
            elapsed_ms=0,
            estimated_cost_usd=0.0,
            confidence_note="image file missing",
        )

    api_key = _api_key()
    if not api_key:
        return SpineRead(
            title="",
            author="",
            raw_text="",
            status="missing_key",
            elapsed_ms=0,
            estimated_cost_usd=0.0,
            confidence_note=f"Set {settings.VLM_API_KEY_ENV} in the environment or .env",
        )

    started = time.perf_counter()
    try:
        raw, prompt_tokens, completion_tokens = _call_provider(path, api_key)
    except TimeoutError as exc:
        elapsed = int((time.perf_counter() - started) * 1000)
        return SpineRead(
            title="",
            author="",
            raw_text=str(exc),
            status="timeout",
            elapsed_ms=elapsed,
            estimated_cost_usd=0.0,
            confidence_note="provider timeout",
        )
    except Exception as exc:
        elapsed = int((time.perf_counter() - started) * 1000)
        name = type(exc).__name__
        status: Status = "timeout" if "Timeout" in name else "api_error"
        return SpineRead(
            title="",
            author="",
            raw_text=f"{name}: {exc}",
            status=status,
            elapsed_ms=elapsed,
            estimated_cost_usd=0.0,
            confidence_note="provider call failed",
        )

    elapsed = int((time.perf_counter() - started) * 1000)
    cost = _estimate_cost(prompt_tokens, completion_tokens)
    print(
        f"[vlm] provider=cursor-cloud model={settings.VLM_MODEL} ms={elapsed} "
        f"prompt_tokens={prompt_tokens} completion_tokens={completion_tokens} "
        f"est_cost_usd={cost:.6f} (0 = included in Cursor plan / unknown)"
    )

    parsed = _parse_spine_json(raw)
    if parsed is None:
        return SpineRead(
            title="",
            author="",
            raw_text=raw,
            status="unreadable",
            elapsed_ms=elapsed,
            estimated_cost_usd=cost,
            confidence_note="malformed JSON from VLM",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    title, author, note = parsed
    if not title:
        return SpineRead(
            title="",
            author=author,
            raw_text=raw,
            status="unreadable",
            elapsed_ms=elapsed,
            estimated_cost_usd=cost,
            confidence_note=note or "empty title",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )

    return SpineRead(
        title=title,
        author=author,
        raw_text=raw,
        status="ok",
        elapsed_ms=elapsed,
        estimated_cost_usd=cost,
        confidence_note=note,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )


def apply_spine_read(spine, result: SpineRead) -> None:
    """Write a SpineRead onto a DetectedSpine row (does not touch ShelfPhoto)."""
    spine.vlm_title = result.title
    spine.vlm_author = result.author
    spine.vlm_raw_response = result.raw_text
    spine.vlm_status = "OK" if result.status == "ok" else "UNREADABLE"
    spine.save(
        update_fields=[
            "vlm_title",
            "vlm_author",
            "vlm_raw_response",
            "vlm_status",
        ]
    )


def read_spines_for_photo(photo, *, limit: int | None = None) -> list[SpineRead]:
    """
    Run VLM on crop files for a ShelfPhoto. Accumulates sum(elapsed_ms) into
    photo.vlm_ms — that per-image total is what the README latency table needs.
    """
    results: list[SpineRead] = []
    total_ms = 0
    spines = list(photo.spines.all())
    if limit is not None:
        spines = spines[:limit]

    for spine in spines:
        if not spine.crop:
            read = SpineRead(
                title="",
                author="",
                raw_text="",
                status="unreadable",
                elapsed_ms=0,
                estimated_cost_usd=0.0,
                confidence_note="missing crop file",
            )
            apply_spine_read(spine, read)
            results.append(read)
            continue
        read = read_spine(spine.crop.path)
        apply_spine_read(spine, read)
        total_ms += read.elapsed_ms
        results.append(read)

    photo.vlm_ms = total_ms
    photo.save(update_fields=["vlm_ms"])
    return results
