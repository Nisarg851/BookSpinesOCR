# Shelfie

Photo of a bookshelf → structured personal library.

This is a local-only take-home: Expo (React Native) client + Django REST API. No deployment.

## Status

Local book detection is wired end-to-end: Expo can capture / pick / URL-submit a photo, Django runs Ultralytics YOLOv8n (COCO, CPU), and the app shows crop thumbnails + boxes. VLM reading, fuzzy matching, and review UI are not built yet.

## Stack (local vs hosted)

| Piece | Where it runs |
| --- | --- |
| Spine/book detection (YOLOv8n, COCO pretrained, CPU) | Local |
| Title/author read from spine crops | Hosted VLM (not wired yet; provider TBD) |
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
- `GET /api/library/`
- `POST /api/detect/` — multipart `image` **or** JSON `{"url":"..."}` (original is not kept; crops are)
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

VLM cost: not applicable yet.

Honest caveat: COCO `book` is not a spine segmenter — one detection may cover a cluster of spines.

## What's unfinished

VLM per-crop reads, fuzzy catalog matching, review screen, library confirm flow, matching tests, fuller README tradeoffs.
