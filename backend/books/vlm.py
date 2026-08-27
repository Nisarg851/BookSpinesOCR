"""
Hosted vision-language spine reader.

Primary: OpenAI Chat Completions vision (gpt-4o-mini).
Fallback: Cursor Cloud Agents when OpenAI fails or VLM_PROVIDER=cursor.

`read_spine()` stays public. API keys from repo-root .env — never hardcode.
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
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from django.conf import settings

Status = Literal["ok", "unreadable", "timeout", "api_error", "missing_key"]

CURSOR_API_BASE = "https://api.cursor.com/v1"
OPENAI_API_BASE = "https://api.openai.com/v1"

# Rough gpt-4o-mini vision list prices (USD / 1M tokens) for logging only.
INPUT_USD_PER_1M = 0.15
OUTPUT_USD_PER_1M = 0.60

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


def _env_key(name: str) -> str | None:
    _load_repo_dotenv()
    key = os.environ.get(name, "").strip()
    return key or None


def _openai_key() -> str | None:
    return _env_key("OPENAI_API_KEY")


def _cursor_key() -> str | None:
    return _env_key("CURSOR_API_KEY")


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


def _image_payload(image_path: Path) -> tuple[str, str]:
    mime, _ = mimetypes.guess_type(str(image_path))
    if mime not in {"image/jpeg", "image/png", "image/gif", "image/webp"}:
        mime = "image/jpeg"
    image_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return mime, image_b64


def _call_openai(image_path: Path, api_key: str) -> tuple[str, int, int]:
    """
    OpenAI Chat Completions vision adapter.
    Returns (raw_content, prompt_tokens, completion_tokens).
    """
    mime, image_b64 = _image_payload(image_path)
    body = {
        "model": settings.VLM_MODEL,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": SPINE_PROMPT},
                    {
                        "type": "image_url",
                        # detail=low keeps TPM cost tiny (full crops were ~14k
                        # tokens each and blew a 60k TPM free-tier limit).
                        "image_url": {
                            "url": f"data:{mime};base64,{image_b64}",
                            "detail": "low",
                        },
                    },
                ],
            }
        ],
    }

    last_error: Exception | None = None
    for attempt in range(4):
        req = urllib.request.Request(
            f"{OPENAI_API_BASE}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(
                req, timeout=float(settings.VLM_TIMEOUT_S)
            ) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            last_error = RuntimeError(
                f"OpenAI API HTTP {exc.code}: {detail[:500]}"
            )
            # Retry brief TPM / rate-limit windows.
            if exc.code == 429 and attempt < 3:
                wait_s = 1.5 * (attempt + 1)
                time.sleep(wait_s)
                continue
            raise last_error from exc
        except urllib.error.URLError as exc:
            raise TimeoutError(str(exc)) from exc
    else:
        raise last_error or RuntimeError("OpenAI request failed")

    choices = payload.get("choices") or []
    if not choices:
        raise RuntimeError(f"OpenAI returned no choices: {payload!r}"[:500])
    message = (choices[0] or {}).get("message") or {}
    raw = str(message.get("content") or "").strip()
    if not raw:
        raise RuntimeError(f"OpenAI returned empty content: {payload!r}"[:500])

    usage = payload.get("usage") or {}
    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)
    return raw, prompt_tokens, completion_tokens



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
    """Cloud Agents REST adapter (slow fallback)."""
    mime, image_b64 = _image_payload(image_path)

    created = _cursor_request(
        "POST",
        "/agents",
        api_key,
        body={
            "prompt": {
                "text": SPINE_PROMPT,
                "images": [{"data": image_b64, "mimeType": mime}],
            },
            "model": {
                "id": getattr(settings, "VLM_CURSOR_MODEL", None) or "default"
            },
            "name": "shelfie-spine-read",
        },
        timeout=float(settings.VLM_TIMEOUT_S),
    )
    agent = created.get("agent") or {}
    run = created.get("run") or {}
    agent_id = agent.get("id")
    run_id = run.get("id")
    if not agent_id or not run_id:
        raise RuntimeError(f"Unexpected create response: {created!r}")

    deadline = time.monotonic() + float(settings.VLM_TIMEOUT_S)
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = _cursor_request(
            "GET",
            f"/agents/{agent_id}/runs/{run_id}",
            api_key,
            timeout=60.0,
        )
        status = (last.get("status") or "").upper()
        if status in {"FINISHED", "ERROR", "CANCELLED", "EXPIRED"}:
            break
        time.sleep(1.5)
    else:
        raise TimeoutError(
            f"Cursor run {run_id} did not finish within {settings.VLM_TIMEOUT_S}s"
        )

    status = (last.get("status") or "").upper()
    raw = (last.get("result") or "").strip()
    if status != "FINISHED":
        raise RuntimeError(f"Cursor run status={status} result={raw[:300]!r}")

    try:
        _cursor_request("POST", f"/agents/{agent_id}/archive", api_key, body={})
    except Exception:
        pass

    return raw, 0, 0


def _call_provider(image_path: Path) -> tuple[str, int, int, str]:
    """
    Call primary provider, with Cursor fallback when using OpenAI.
    Returns (raw, prompt_tokens, completion_tokens, provider_used).
    """
    provider = (settings.VLM_PROVIDER or "openai").strip().lower()

    if provider == "cursor":
        key = _cursor_key()
        if not key:
            raise RuntimeError("CURSOR_API_KEY missing")
        raw, pt, ct = _call_cursor(image_path, key)
        return raw, pt, ct, "cursor"

    openai_key = _openai_key()
    cursor_key = _cursor_key()
    if not openai_key and not cursor_key:
        raise RuntimeError(
            "VLM API key missing — set OPENAI_API_KEY (or CURSOR_API_KEY fallback)"
        )

    if openai_key:
        try:
            raw, pt, ct = _call_openai(image_path, openai_key)
            return raw, pt, ct, "openai"
        except Exception as openai_exc:
            if not cursor_key:
                raise
            print(f"[vlm] openai failed ({openai_exc}); falling back to cursor")
            raw, pt, ct = _call_cursor(image_path, cursor_key)
            return raw, pt, ct, "cursor-fallback"

    raw, pt, ct = _call_cursor(image_path, cursor_key)  # type: ignore[arg-type]
    return raw, pt, ct, "cursor"


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
            confidence_note="Spine crop file is missing on disk",
        )

    if not _openai_key() and not _cursor_key():
        return SpineRead(
            title="",
            author="",
            raw_text="",
            status="missing_key",
            elapsed_ms=0,
            estimated_cost_usd=0.0,
            confidence_note=(
                "VLM API key missing — set OPENAI_API_KEY "
                "(Cursor CURSOR_API_KEY is the fallback)"
            ),
        )

    started = time.perf_counter()
    provider_used = settings.VLM_PROVIDER
    try:
        raw, prompt_tokens, completion_tokens, provider_used = _call_provider(path)
    except TimeoutError as exc:
        elapsed = int((time.perf_counter() - started) * 1000)
        return SpineRead(
            title="",
            author="",
            raw_text=str(exc),
            status="timeout",
            elapsed_ms=elapsed,
            estimated_cost_usd=0.0,
            confidence_note="Title reading timed out",
        )
    except Exception as exc:
        elapsed = int((time.perf_counter() - started) * 1000)
        name = type(exc).__name__
        detail = str(exc)
        status: Status = "timeout" if "Timeout" in name else "api_error"
        lower = detail.lower()
        if "insufficient_quota" in lower or "exceeded your current quota" in lower:
            note = (
                "OpenAI quota exceeded (and Cursor fallback unavailable) — "
                "add billing at platform.openai.com or set CURSOR_API_KEY"
            )
        elif "429" in detail and "rate" in lower:
            note = "Title reader rate-limited — wait a moment and retry"
        elif "Timeout" in name or status == "timeout":
            note = "Title reading timed out"
        else:
            note = "Title reader failed (API error)"
        return SpineRead(
            title="",
            author="",
            raw_text=f"{name}: {exc}",
            status=status,
            elapsed_ms=elapsed,
            estimated_cost_usd=0.0,
            confidence_note=note,
        )

    elapsed = int((time.perf_counter() - started) * 1000)
    cost = _estimate_cost(prompt_tokens, completion_tokens)
    print(
        f"[vlm] provider={provider_used} model={settings.VLM_MODEL} "
        f"ms={elapsed} prompt_tokens={prompt_tokens} "
        f"completion_tokens={completion_tokens} est_cost_usd={cost:.6f}"
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
            confidence_note="Title reader returned invalid (non-JSON) text",
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
            confidence_note=note or "Title reader returned no title",
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


# Persisted at the start of vlm_raw_response so the API can surface a short reason
# without a schema migration.
_VLM_NOTE_PREFIX = "VLM_NOTE:"


def apply_spine_read(spine, result: SpineRead) -> None:
    """Write a SpineRead onto a DetectedSpine row (does not touch ShelfPhoto)."""
    spine.vlm_title = result.title
    spine.vlm_author = result.author
    if result.status == "ok":
        spine.vlm_raw_response = result.raw_text
    else:
        note = result.confidence_note or result.status
        spine.vlm_raw_response = f"{_VLM_NOTE_PREFIX}{note}\n{result.raw_text}"
    spine.vlm_status = "OK" if result.status == "ok" else "UNREADABLE"
    spine.save(
        update_fields=[
            "vlm_title",
            "vlm_author",
            "vlm_raw_response",
            "vlm_status",
        ]
    )


def extract_vlm_note(raw_response: str, vlm_status: str) -> str:
    """Short user-facing reason for a failed/unread spine read."""
    raw = raw_response or ""
    if raw.startswith(_VLM_NOTE_PREFIX):
        return raw.split("\n", 1)[0][len(_VLM_NOTE_PREFIX) :].strip()
    if vlm_status == "UNREADABLE":
        return "Couldn’t read a title from this spine"
    return ""


def _read_one_spine(spine) -> tuple[Any, SpineRead]:
    if not spine.crop:
        read = SpineRead(
            title="",
            author="",
            raw_text="",
            status="unreadable",
            elapsed_ms=0,
            estimated_cost_usd=0.0,
            confidence_note="Missing spine crop file",
        )
        return spine, read
    return spine, read_spine(spine.crop.path)


def read_spines_for_photo(photo, *, limit: int | None = None) -> list[SpineRead]:
    """
    Run VLM on crop files for a ShelfPhoto. Accumulates sum(elapsed_ms) into
    photo.vlm_ms — that per-image total is what the README latency table needs.

    OpenAI/Gemini calls are parallelized (thread pool); Cursor stays sequential.
    """
    spines = list(photo.spines.all())
    if limit is not None:
        spines = spines[:limit]
    if not spines:
        photo.vlm_ms = 0
        photo.save(update_fields=["vlm_ms"])
        return []

    provider = (settings.VLM_PROVIDER or "openai").strip().lower()
    if provider == "cursor":
        workers = 1
    else:
        workers = min(3, len(spines))

    results_by_id: dict[int, SpineRead] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_read_one_spine, spine) for spine in spines]
        for future in as_completed(futures):
            spine, read = future.result()
            apply_spine_read(spine, read)
            results_by_id[spine.id] = read

    ordered = [results_by_id[s.id] for s in spines]
    photo.vlm_ms = sum(r.elapsed_ms for r in ordered)
    photo.save(update_fields=["vlm_ms"])
    return ordered
