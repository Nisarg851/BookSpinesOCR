# Shelfie

Photo of a bookshelf → structured personal library.

This is a local-only take-home: Expo (React Native) client + Django REST API. No deployment.

## Status

End-to-end API is wired: `POST /api/photos/` runs detect → VLM → match synchronously and returns spines with MatchResults + latency. Confirm/correct/discard and library list work. Expo shows titles, match status, and latency. A dedicated review-screen UX polish and fuller README tradeoffs remain.

## Stack (local vs hosted)

| Piece | Where it runs |
| --- | --- |
| Spine/book detection (YOLOv8n, COCO pretrained, CPU) | Local |
| Title/author read from spine crops | Hosted — Cursor Cloud Agents (`composer-2.5`) |
| Catalog match + library | Local SQLite (catalog loaded; matching not wired yet) |

## Setup

### Backend

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
cd backend
python manage.py migrate
python manage.py load_catalog
python manage.py runserver 0.0.0.0:8000
```

First detection download: Ultralytics fetches `yolov8n.pt` into `backend/models/` (gitignored).

Smoke-test detection without the API:

```powershell
python manage.py detect_spines samples\bookshelf.jpg
```

Endpoints:
- `GET /api/health/`
- `GET /api/catalog/`
- `POST /api/photos/` — multipart `image` **or** JSON `{"url":"..."}`; runs detect → VLM → match synchronously
- `GET /api/photos/<id>/` — refetch photo + spines + matches + latency
- `POST /api/spines/<id>/confirm/` — `{action: accept|correct|discard}`
- `GET /api/library/` — confirmed LibraryEntry rows
- `/admin/` — `python manage.py createsuperuser`

### Mobile (Expo)

```powershell
cd mobile
npm install
npx expo start
```

On a **physical device**, create `mobile/.env` from `.env.example` with your PC Wi‑Fi IP, then restart Expo.

## Catalog

`catalog.csv` has ~130 books with deliberate ambiguities. Load with `python manage.py load_catalog`.

## Measured latency / cost

Sample photo `samples/bookshelf.jpg` (management command, CPU, YOLOv8n):

| Stage | Measured |
| --- | --- |
| Detection (first warm-ish run after weight download) | ~7.3 s |
| Detection (subsequent API smoke test) | ~3.9 s |
| Boxes / crops | 47 |

VLM (Cursor Cloud Agents, model `default` / Auto, no-repo). Measured on three real crops from `backend/media/crops/1/`:

| Crop | Title / author returned | `vlm_ms` |
| --- | --- | --- |
| `3.jpg` | Water for Elephants / Sara Gruen | ~63.5 s |
| `10.jpg` | INTO THIN AIR / Jon Krakauer | ~65.4 s |
| `24.jpg` | STATION ELEVEN / EMILY ST. JOHN MANDEL | ~65.5 s |

Per-call cost logged as `$0` (Cursor plan / no token meter on this API). Cap: `VLM_MAX_SPINES_PER_PHOTO` (default 8). Requires `CURSOR_API_KEY` in repo-root `.env` and Cloud Agent storage enabled.

Honest caveat: COCO `book` is not a spine segmenter — one detection may cover a cluster of spines.

## What's unfinished

VLM per-crop reads, fuzzy catalog matching, review screen, library confirm flow, matching tests, fuller README tradeoffs.
