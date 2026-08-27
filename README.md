# catalog.csv

A catalog of approximately 130 realworld books.

## Fields

| Field       | Description                                                                 |
|-------------|-------------------------------------------------------------------------------|
| `id`        | Unique row identifier.                                                        |
| `title`     | Title as it appears on that edition.                                          |
| `author`    | Author name, in whatever form that edition uses.|
| `alt_titles`| Known alternate title(s) for the same book — a different-language original, a US/UK retitle, or a short form. Blank when no alternate is known. |
| `isbn13`    | 13-digit ISBN, where one exists. Blank for editions that predate ISBN standardization or otherwise lack one. |
| `publisher` | Publisher of that specific edition.                                           |
| `year`      | Publication year of that edition.                                             |
| `edition`   | Edition label, e.g. "1st ed.", "Penguin Classics", "UK 1st ed."               |

## Stats

- 130 rows total
- 12 distinct titles appear twice each (24 rows) — see "Characteristics" below
- 114/130 rows have an ISBN; 16 have none
- 41/130 rows have `alt_titles` populated; the rest are blank

## Characteristics

**Duplicate editions of the same book.** The same title/author pair appears twice
with different `edition`, `year`, `isbn13`, or `publisher` — e.g. *Pride and
Prejudice* (1813, T. Egerton, no ISBN) and *Pride and Prejudice* (2003, Penguin
Classics, with ISBN).

**Same book under a different title.** US/UK retitles and translations, linked via
`alt_titles` rather than a shared `title`. E.g. *Harry Potter and the Philosopher's
Stone* ↔ *...and the Sorcerer's Stone*; *Cien años de soledad* ↔ *One Hundred Years
of Solitude*.

**Different books that share a title.** Same `title`, unrelated `author`. E.g. two
entries titled *Foundation* — one Isaac Asimov's science fiction novel, one Peter
Ackroyd's history of England — and two entries titled *The Stranger*, by Albert
Camus and Harlan Coben respectively.

**Omnibus editions alongside individual volumes.** E.g. *The Lord of the Rings*
(one-volume omnibus) appears as its own row alongside separate rows for *The
Fellowship of the Ring*, *The Two Towers*, and *The Return of the King*.

**Titles that are substrings of other titles.** Short, generic titles (*It*, *Us*,
*Kim*, *Room*) sit alongside longer titles that contain them (*A Room with a
View*, *Circle of Friends*, *Gone with the Wind*).

**Author names in inconsistent formats.** Initials vs. full name (*J.K. Rowling*
vs. *Rowling, J.K.*), accented vs. unaccented (*García Márquez* vs. *Garcia
Marquez*, *Brontë* vs. *Bronte*), transliteration variants (*Dostoevsky* vs.
*Dostoyevsky*, *Leo Tolstoy* vs. *Lev Tolstoy*), and pen names vs. legal names
(*George Orwell* vs. *Eric Arthur Blair*).
