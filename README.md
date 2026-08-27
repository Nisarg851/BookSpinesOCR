# Book Spines OCR

Photo of a bookshelf → structured personal library (local take-home).

**Expo (React Native/TypeScript) client** + **Django REST API** + **SQLite**. No deploy/auth/CI required.

## What it does

1. Capture / pick / URL-upload a shelf photo  
2. Local YOLO detects book-like regions and crops them  
3. Hosted VLM reads title/author per crop (**OpenAI `gpt-4o-mini`**, **Cursor Cloud Agents** as automatic fallback)  
4. Fuzzy-match against `catalog.csv`  
5. Human-in-the-loop review (accept / correct / discard)  
6. Confirmed books land in the library list  

## Stack

| Piece | Where |
| --- | --- |
| Detection — Ultralytics YOLOv8n (COCO `book`, CPU, no training) | Local |
| Spine title/author VLM | Hosted OpenAI (primary) / Cursor (fallback) |
| Catalog match (`rapidfuzz`) + library | Local SQLite |
| Mobile UI | Expo |

**Honest limit:** COCO `book` is not a per-spine segmenter — one box may cover a cluster of spines. The review UI is designed for that messiness.

## Setup

### Secrets (never commit)

Copy `.env.example` → `.env` at the repo root:

```
VLM_PROVIDER=openai
VLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...
CURSOR_API_KEY=crsr_...   # optional fallback
```

Force Cursor only with `VLM_PROVIDER=cursor`.

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

First detection run downloads `yolov8n.pt` into `backend/models/` (gitignored).

### Mobile

```powershell
cd mobile
npm install
# Physical phone: copy mobile/.env.example → mobile/.env with your LAN IP
npx expo start
```

## API

| Method | Path | Notes |
| --- | --- | --- |
| `GET` | `/api/health/` | Reachability |
| `GET` | `/api/catalog/` | Catalog books |
| `POST` | `/api/photos/` | Multipart `image` **or** JSON `{"url":"..."}`; sync detect→VLM→match |
| `GET` | `/api/photos/<id>/` | Refetch + latency |
| `POST` | `/api/spines/<id>/confirm/` | `{action: accept\|correct\|discard}` |
| `GET` | `/api/library/` | Confirmed entries |

Zero detections / failed VLMs return **200** with an empty or partial spine list (not a 500). Corrupt images / model load failures return **422** with a structured message.

Latency fields on photo responses: `detection_ms`, `vlm_ms`, `matching_ms`, `total_ms`.

## App screens

- **Capture** — camera, device library, or image URL; health badge; loading state  
- **Review** — HITL for each spine; auto-matches can be removed before Done writes the library  
- **Library** — pull-to-refresh list of confirmed books  

## Catalog

`catalog.csv` (~130 rows) includes deliberate ambiguities (e.g. same title / different authors, US/UK retitles as `alt_titles`). Load with `python manage.py load_catalog` (idempotent).

Matcher tests: `python manage.py test books.tests`

## Latency notes

| Stage | Typical |
| --- | --- |
| Detection (CPU YOLO) | ~4–8 s |
| VLM OpenAI (detail=low, parallel ≤3) | ~1 s / crop → often tens of seconds for a shelf |
| VLM Cursor fallback | ~1 min / crop (much slower) |
| Matching | &lt;1 s |

Cap spines per photo with `VLM_MAX_SPINES_PER_PHOTO` (default 8).

## Tradeoffs / “another day”

- COCO detection ≠ spine instance segmentation — a trained spine model would help recall/precision  
- Sync pipeline blocks the HTTP request (fine for the exercise; queue/workers for production)  
- No auth, multi-user library, or deployment  
- OpenAI TPM limits on free/low tiers — we use `detail=low`, retries, and modest parallelism  

## Samples

`samples/bookshelf.jpg` is the default smoke photo:

```powershell
python manage.py detect_spines samples\bookshelf.jpg
```
