"""
Real matcher tests against rows that exist in catalog.csv.

Messiness covered (one case each, pulled from the CSV — not invented):
1. Duplicate editions of the same book
2. Same book under different titles (US/UK)
3. Different books sharing a title
4. Omnibus vs individual volume
5. Substring titles
6. Author name form variants (comma order, accents)
"""

from __future__ import annotations

import csv
from pathlib import Path

from django.test import SimpleTestCase, override_settings

from books.matching import CatalogEntry, match_book, normalize_author, normalize_title

CATALOG_CSV = Path(__file__).resolve().parents[2] / "catalog.csv"


def load_catalog() -> list[CatalogEntry]:
    entries: list[CatalogEntry] = []
    with CATALOG_CSV.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            entries.append(
                CatalogEntry(
                    id=int(row["id"]),
                    title=row["title"],
                    author=row["author"],
                    alt_titles=row.get("alt_titles") or "",
                )
            )
    return entries


@override_settings(
    MATCH_AUTO_ACCEPT_THRESHOLD=0.88,
    MATCH_REVIEW_FLOOR=0.55,
    MATCH_AMBIGUITY_GAP=0.08,
)
class MatcherNormalizationTests(SimpleTestCase):
    def test_author_comma_order_normalizes_equal(self):
        # catalog id=70 author is "Rowling, J.K."
        self.assertEqual(
            normalize_author("Rowling, J.K."),
            normalize_author("J.K. Rowling"),
        )

    def test_accent_folding(self):
        # catalog id=13 "Charlotte Brontë" vs id=14 "Charlotte Bronte"
        self.assertEqual(
            normalize_author("Charlotte Brontë"),
            normalize_author("Charlotte Bronte"),
        )


@override_settings(
    MATCH_AUTO_ACCEPT_THRESHOLD=0.88,
    MATCH_REVIEW_FLOOR=0.55,
    MATCH_AMBIGUITY_GAP=0.08,
)
class MatcherCatalogMessinessTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.catalog = load_catalog()
        assert len(cls.catalog) >= 100

    def _by_id(self, book_id: int) -> CatalogEntry:
        return next(e for e in self.catalog if e.id == book_id)

    def test_duplicate_editions_same_book(self):
        """
        CSV ids 1 and 2: Pride and Prejudice / Jane Austen, two editions.
        A clean VLM read should land on *a* Pride and Prejudice Austen row
        with high confidence (edition choice is secondary for this exercise).
        """
        decision = match_book(
            "Pride and Prejudice",
            "Jane Austen",
            self.catalog,
        )
        self.assertIsNotNone(decision.best)
        self.assertIn(decision.best.entry.id, {1, 2})
        self.assertEqual(decision.best.entry.author, "Jane Austen")
        self.assertGreaterEqual(decision.best.confidence, 0.88)
        self.assertEqual(decision.status, "AUTO_ACCEPTED")

    def test_us_uk_alternate_title(self):
        """
        CSV ids 19/20: Philosopher's Stone ↔ Sorcerer's Stone via alt_titles.
        Querying the US title must hit a Harry Potter Rowling row (via alt or
        primary), not fail exact-string match.
        """
        decision = match_book(
            "Harry Potter and the Sorcerer's Stone",
            "J.K. Rowling",
            self.catalog,
        )
        self.assertIsNotNone(decision.best)
        self.assertIn(decision.best.entry.id, {19, 20})
        self.assertIn("Rowling", decision.best.entry.author)
        self.assertGreaterEqual(decision.best.confidence, 0.88)
        self.assertEqual(decision.status, "AUTO_ACCEPTED")

    def test_shared_title_different_books_disambiguated_by_author(self):
        """
        CSV ids 37/38: Foundation — Asimov SF vs Ackroyd history.
        Author must pick the right one; runner-up should be the other Foundation.
        """
        decision = match_book("Foundation", "Isaac Asimov", self.catalog)
        self.assertIsNotNone(decision.best)
        self.assertEqual(decision.best.entry.id, 37)
        self.assertEqual(decision.best.entry.author, "Isaac Asimov")
        self.assertIsNotNone(decision.runner_up)
        self.assertEqual(decision.runner_up.entry.id, 38)
        # Asimov must clearly beat Ackroyd on confidence.
        self.assertGreater(
            decision.best.confidence - decision.runner_up.confidence,
            0.08,
        )

    def test_shared_title_ambiguous_when_author_missing(self):
        """
        Same Foundation pair, but empty author — should not auto-accept and
        should surface ambiguity between the two Foundation rows.
        """
        decision = match_book("Foundation", "", self.catalog)
        self.assertIsNotNone(decision.best)
        self.assertIn(decision.best.entry.id, {37, 38})
        self.assertTrue(decision.ambiguous)
        self.assertEqual(decision.status, "PENDING_REVIEW")
        self.assertIsNotNone(decision.runner_up)
        self.assertIn(decision.runner_up.entry.id, {37, 38})
        self.assertNotEqual(decision.best.entry.id, decision.runner_up.entry.id)

    def test_omnibus_vs_individual_volume(self):
        """
        CSV ids 47 (LOTR omnibus) vs 48 (Fellowship).
        A Fellowship spine must prefer the volume, not the omnibus.
        """
        decision = match_book(
            "The Fellowship of the Ring",
            "J.R.R. Tolkien",
            self.catalog,
        )
        self.assertIsNotNone(decision.best)
        self.assertEqual(decision.best.entry.id, 48)
        self.assertNotEqual(decision.best.entry.id, 47)

    def test_substring_title_does_not_steal_short_query(self):
        """
        CSV ids 60 (Room / Donoghue) vs 61 (A Room with a View / Forster).
        Query 'Room' + Donoghue must not prefer the longer Forster title.
        """
        decision = match_book("Room", "Emma Donoghue", self.catalog)
        self.assertIsNotNone(decision.best)
        self.assertEqual(decision.best.entry.id, 60)
        self.assertEqual(decision.best.entry.title, "Room")

    def test_author_lastname_firstname_order(self):
        """
        CSV id=70: author stored as "Rowling, J.K."
        VLM-style "J.K. Rowling" must still match Chamber of Secrets.
        """
        row = self._by_id(70)
        self.assertEqual(row.author, "Rowling, J.K.")
        decision = match_book(
            "Harry Potter and the Chamber of Secrets",
            "J.K. Rowling",
            self.catalog,
        )
        self.assertIsNotNone(decision.best)
        self.assertEqual(decision.best.entry.id, 70)
        self.assertGreaterEqual(decision.best.confidence, 0.88)
        self.assertEqual(decision.status, "AUTO_ACCEPTED")

    def test_author_accent_variant(self):
        """
        CSV id=13 uses Brontë; unaccented VLM author should still match.
        """
        decision = match_book(
            "Jane Eyre",
            "Charlotte Bronte",
            self.catalog,
        )
        self.assertIsNotNone(decision.best)
        self.assertIn(decision.best.entry.id, {13, 14})
        self.assertGreaterEqual(decision.best.confidence, 0.85)

    def test_translated_alt_title(self):
        """
        CSV ids 29/30: Cien años de soledad ↔ One Hundred Years of Solitude.
        English query should match via alt_titles on the Spanish row or the
        English primary row.
        """
        decision = match_book(
            "One Hundred Years of Solitude",
            "Gabriel Garcia Marquez",
            self.catalog,
        )
        self.assertIsNotNone(decision.best)
        self.assertIn(decision.best.entry.id, {29, 30})
        self.assertGreaterEqual(decision.best.confidence, 0.80)

    def test_low_confidence_stays_pending_never_dropped(self):
        """Garbage query still returns a decision the UI can show."""
        decision = match_book("zzzz-not-a-real-book-qqq", "Nobody Known", self.catalog)
        self.assertEqual(decision.status, "PENDING_REVIEW")
        self.assertFalse(decision.suggested)
        # best may exist as a weak top hit — never silently None-out the status path
        self.assertIsNotNone(decision.best)
        self.assertLess(decision.best.confidence, 0.55)
