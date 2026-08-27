"""
Fuzzy catalog matcher for VLM {title, author} guesses.

Survives the messiness deliberately baked into catalog.csv:
duplicate titles, multi-editions, alt/translated titles, author-name
variants, substring titles, and omnibus-vs-volume rows.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, Sequence

from django.conf import settings
from rapidfuzz import fuzz

# ---------------------------------------------------------------------------
# Confidence formula (defend this live):
#
#   title_score  = best rapidfuzz score of query title vs (primary title ∪
#                  each alt_title), scaled 0–1. We take the max of
#                  fuzz.ratio and (token_set_ratio * length_ratio) so word
#                  reordering still scores well, but a short query that is
#                  merely a substring of a longer title (e.g. "Room" ⊂
#                  "A Room with a View") is down-weighted by length_ratio.
#
#   author_score = best of fuzz.token_set_ratio / fuzz.ratio on normalized
#                  author forms (handles "Last, First" vs "First Last" and
#                  initials after we normalize commas / punctuation), 0–1.
#
#   confidence   = 0.62 * title_score + 0.38 * author_score
#                  + 0.05 if exact normalized title match AND author_score ≥ 0.80
#                  (capped at 1.0)
#
# Title weighs more than author because spines often omit or truncate
# authors, but author is heavy enough that two books sharing a title
# (Foundation / The Stranger) are separated by author_score. Exact-title
# bonus rewards clean OCR without letting a wrong author auto-accept.
# ---------------------------------------------------------------------------

_TITLE_WEIGHT = 0.62
_AUTHOR_WEIGHT = 0.38
_EXACT_TITLE_BONUS = 0.05
_EXACT_TITLE_AUTHOR_FLOOR = 0.80


@dataclass(frozen=True)
class CatalogEntry:
    """Plain catalog row — keeps matching independent of Django ORM."""

    id: int
    title: str
    author: str
    alt_titles: str = ""


@dataclass(frozen=True)
class ScoredMatch:
    entry: CatalogEntry
    confidence: float
    title_score: float
    author_score: float
    matched_title: str  # which title string won (primary or an alt)


@dataclass(frozen=True)
class MatchDecision:
    """Outcome of matching one VLM guess against the catalog."""

    best: ScoredMatch | None
    runner_up: ScoredMatch | None
    ambiguous: bool
    status: str  # AUTO_ACCEPTED | PENDING_REVIEW
    suggested: bool  # True when PENDING_REVIEW but we still have a best guess

    @property
    def confidence(self) -> float:
        return self.best.confidence if self.best else 0.0


_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_SPACE_RE = re.compile(r"\s+")
_SUBTITLE_RE = re.compile(r"\s*[:;—–-]\s+.*$")


def normalize_text(value: str, *, strip_subtitle: bool = False) -> str:
    """Lowercase, fold accents, drop punctuation; optionally cut after colon."""
    text = (value or "").strip()
    if not text:
        return ""
    # NFKD + drop combining marks → "Brontë" / "García" become ASCII-ish.
    decomposed = unicodedata.normalize("NFKD", text)
    folded = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    folded = folded.lower()
    if strip_subtitle:
        folded = _SUBTITLE_RE.sub("", folded)
    folded = _PUNCT_RE.sub(" ", folded)
    return _SPACE_RE.sub(" ", folded).strip()


def normalize_author(value: str) -> str:
    """
    Normalize author for comparison.

    "Rowling, J.K." → "j k rowling"
    "J.K. Rowling"  → "j k rowling"
    "Leo Tolstoy" / "Lev Tolstoy" stay distinct after accent fold only —
    transliteration aliases are a catalog/alt problem, not this function.
    """
    text = (value or "").strip()
    if not text:
        return ""
    # "Lastname, Firstname [Middle]" → "Firstname [Middle] Lastname"
    if "," in text:
        last, _, rest = text.partition(",")
        text = f"{rest.strip()} {last.strip()}".strip()
    return normalize_text(text)


def normalize_title(value: str) -> str:
    """Title normalize; keep subtitle by default so editions stay distinguishable."""
    return normalize_text(value, strip_subtitle=False)


def _length_ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    return len(shorter) / len(longer)


def _title_similarity(query: str, candidate: str) -> float:
    if not query or not candidate:
        return 0.0
    if query == candidate:
        return 1.0
    ratio = fuzz.ratio(query, candidate) / 100.0
    token = fuzz.token_set_ratio(query, candidate) / 100.0
    # Penalize token_set inflation when one string is much shorter (substring trap).
    token_adj = token * (0.35 + 0.65 * _length_ratio(query, candidate))
    return max(ratio, token_adj)


def _author_similarity(query: str, candidate: str) -> float:
    if not query and not candidate:
        return 1.0  # both missing — don't punish title-only spines
    if not query or not candidate:
        return 0.0
    if query == candidate:
        return 1.0
    return max(
        fuzz.ratio(query, candidate) / 100.0,
        fuzz.token_set_ratio(query, candidate) / 100.0,
    )


def _alt_title_list(raw: str) -> list[str]:
    if not raw or not raw.strip():
        return []
    # catalog uses ";" or occasional extra commas inside quotes — split on ";"
    parts = re.split(r"[;|]", raw)
    return [p.strip() for p in parts if p.strip()]


def _score_entry(
    query_title: str,
    query_author: str,
    entry: CatalogEntry,
) -> ScoredMatch:
    q_title = normalize_title(query_title)
    q_author = normalize_author(query_author)

    title_candidates = [entry.title, *_alt_title_list(entry.alt_titles)]
    best_title_score = 0.0
    matched_title = entry.title
    for cand in title_candidates:
        n = normalize_title(cand)
        score = _title_similarity(q_title, n)
        if score > best_title_score:
            best_title_score = score
            matched_title = cand

    author_score = _author_similarity(q_author, normalize_author(entry.author))

    confidence = _TITLE_WEIGHT * best_title_score + _AUTHOR_WEIGHT * author_score
    if best_title_score >= 0.999 and author_score >= _EXACT_TITLE_AUTHOR_FLOOR:
        confidence = min(1.0, confidence + _EXACT_TITLE_BONUS)

    return ScoredMatch(
        entry=entry,
        confidence=round(confidence, 4),
        title_score=round(best_title_score, 4),
        author_score=round(author_score, 4),
        matched_title=matched_title,
    )


def match_book(
    title: str,
    author: str,
    catalog: Sequence[CatalogEntry],
) -> MatchDecision:
    """
    Find the best CatalogEntry for a VLM guess.

    Always returns a MatchDecision the caller can act on — never drops a
    low-confidence result. Status is AUTO_ACCEPTED or PENDING_REVIEW.
    """
    auto_threshold = float(settings.MATCH_AUTO_ACCEPT_THRESHOLD)
    floor = float(settings.MATCH_REVIEW_FLOOR)
    ambiguity_gap = float(settings.MATCH_AMBIGUITY_GAP)

    if not catalog or (not (title or "").strip() and not (author or "").strip()):
        return MatchDecision(
            best=None,
            runner_up=None,
            ambiguous=False,
            status="PENDING_REVIEW",
            suggested=False,
        )

    scored = [_score_entry(title, author, entry) for entry in catalog]
    scored.sort(key=lambda s: s.confidence, reverse=True)

    best = scored[0]
    runner_up = scored[1] if len(scored) > 1 else None

    # Close second is only "ambiguous" when titles collide but authors don't —
    # e.g. Foundation/Asimov vs Foundation/Ackroyd. US/UK retitles of the
    # *same* work (Philosopher's vs Sorcerer's) share an author and should
    # not block auto-accept.
    ambiguous = False
    if (
        runner_up is not None
        and best.confidence - runner_up.confidence <= ambiguity_gap
        and runner_up.confidence >= floor
    ):
        same_title = normalize_title(best.entry.title) == normalize_title(
            runner_up.entry.title
        )
        authors_differ = normalize_author(best.entry.author) != normalize_author(
            runner_up.entry.author
        )
        ambiguous = same_title and authors_differ

    if best.confidence >= auto_threshold and not ambiguous:
        status = "AUTO_ACCEPTED"
        suggested = True
    else:
        status = "PENDING_REVIEW"
        suggested = best.confidence >= floor

    # Below floor: still return best for debugging, but treat as unmatched suggestion.
    if best.confidence < floor:
        suggested = False

    return MatchDecision(
        best=best,
        runner_up=runner_up if ambiguous or (
            runner_up is not None and runner_up.confidence >= floor
        ) else runner_up,
        ambiguous=ambiguous,
        status=status,
        suggested=suggested,
    )


def catalog_entries_from_queryset(qs: Iterable) -> list[CatalogEntry]:
    """Map CatalogBook rows → CatalogEntry."""
    return [
        CatalogEntry(
            id=int(row.id),
            title=row.title,
            author=row.author,
            alt_titles=row.alt_titles or "",
        )
        for row in qs
    ]


def match_against_db(title: str, author: str) -> MatchDecision:
    """Convenience wrapper used by the API / pipeline."""
    from .models import CatalogBook

    entries = catalog_entries_from_queryset(CatalogBook.objects.all())
    return match_book(title, author, entries)
