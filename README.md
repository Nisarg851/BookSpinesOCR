# Book Spines OCR

Photo of a bookshelf → structured personal library.

## Setup (clean clone)

Prereqs: Python 3.11+, Node 20+, a phone with Expo Go (or a simulator).

### 1. Secrets

Copy the example env at the **repo root** (never commit real keys):

```powershell
copy .env.example .env
```

Edit `.env`:

```
VLM_PROVIDER=openai
VLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...
CURSOR_API_KEY=crsr_...   # optional automatic fallback
```

### 2. Backend

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
cd backend
python manage.py migrate
python manage.py load_catalog
python manage.py runserver 0.0.0.0:8000
```

First YOLO run downloads `yolov8n.pt` into `backend/models/` (gitignored).

Smoke the full pipeline on every committed sample photo (needs `OPENAI_API_KEY`):

```powershell
# from repo root, with venv active
python backend\manage.py bench_pipeline
```

### 3. Mobile

```powershell
cd mobile
npm install
copy .env.example .env
# Physical device: set EXPO_PUBLIC_API_URL=http://<your-LAN-IP>:8000
npx expo start
```

Open Expo Go → Capture a shelf (camera / device photo / image URL) → Review → Library.

**Phone can’t reach the API but the PC can?** A Wi‑Fi password ≠ Windows treating the network as Private. If the PC’s Wi‑Fi profile is **Public**, Firewall often **blocks inbound Python** — health works on the PC, fails on the phone. Fix: Settings → Wi‑Fi → your network → set profile to **Private**, or allow TCP **8000** / Python through Windows Firewall. Confirm on the phone browser: `http://<LAN-IP>:8000/api/health/`. Restart Expo after changing `mobile/.env`.

### API (quick reference)

| Method | Path | Notes |
| --- | --- | --- |
| `GET` | `/api/health/` | Reachability |
| `GET` | `/api/catalog/` | Catalog books |
| `POST` | `/api/photos/` | Multipart `image` **or** JSON `{"url":"..."}`; sync detect→VLM→match |
| `GET` | `/api/photos/<id>/` | Refetch + latency |
| `POST` | `/api/spines/<id>/confirm/` | `{action: accept\|correct\|discard}` |
| `GET` | `/api/library/` | Confirmed entries |

Zero detections / failed VLMs return **200** with an empty or partial spine list. Corrupt images / model load failures return **422**.

## Architecture

| Stage | Where | Why |
| --- | --- | --- |
| Book-region detection (Ultralytics **YOLOv8n**, COCO `book`, CPU) | Local | Free, offline, no per-frame API cost; crops shrink what we send upstream |
| Title/author read per crop (**OpenAI `gpt-4o-mini` vision**, `detail=low`) | Hosted | Reading rotated / low-contrast spine text is where a VLM earns its keep |
| Fallback spine read (**Cursor Cloud Agents**) | Hosted | Automatic if OpenAI fails / key missing, or `VLM_PROVIDER=cursor` |
| Fuzzy catalog match (`rapidfuzz`) + library | Local SQLite | Deterministic scoring, free, testable without another model call |

**Split rationale:** detection is high-volume and coarse (many boxes per photo); sending the full shelf image to a VLM would waste tokens and still not give per-spine structure. Crops go to the hosted VLM; matching stays local so catalog ambiguity is under our control.

**Honest detection limit:** COCO `book` is not a per-spine segmenter. One box may cover a cluster of spines. The review UI exists because of that messiness.

Cap: `VLM_MAX_SPINES_PER_PHOTO` (default **8**) — dense shelves detect more boxes than we read.

## Measured latency / cost

Real output from `python backend\manage.py bench_pipeline` on this machine (Windows, CPU YOLO, OpenAI `gpt-4o-mini`, warm weights after the first photo). **Not invented.**

| photo | boxes | vlm_calls | detection_ms | vlm_ms | matching_ms | total_ms | est_cost_usd |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `book-spine.jpg.webp` | 21 | 8 | 4837 | 12899 | 259 | 10223 | $0.0037 |
| `bookshelf.jpg` | 47 | 8 | 189 | 6254 | 498 | 3590 | $0.0037 |
| `Good-Book-Spines.jpg` | 13 | 8 | 170 | 8186 | 170 | 3627 | $0.0037 |
| `Room40B.jpg` | 5 | 5 | 140 | 3941 | 75 | 1974 | $0.0023 |

**How to read the columns**

- `boxes` — YOLO detections before the VLM cap.
- `vlm_calls` — crops actually sent to the VLM (`min(boxes, VLM_MAX_SPINES_PER_PHOTO)`).
- `vlm_ms` — **sum** of per-crop elapsed times (parallelism ≤3, so wall-clock is lower).
- `total_ms` — wall-clock for detect → VLM → match on that photo.
- `est_cost_usd` — sum of OpenAI `usage` tokens × published list rates in code (`$0.15` / `$0.60` per 1M input/output for `gpt-4o-mini`). Cursor fallback would log **$0** (no token meter on that API).

First photo paid cold YOLO load (~4.8 s detection); later photos are warm (~0.14–0.19 s). Re-run `bench_pipeline` after a clean clone to refresh numbers for *your* machine and API tier.

## Catalog

`catalog.csv` (~130 rows) is a hand-built mini bookstore: classics + popular titles, loaded idempotently with `python manage.py load_catalog`.

**Built for messy matching, not for looking clean.** Deliberate ambiguities include:

| Kind | Example in CSV |
| --- | --- |
| Duplicate editions, same title/author | *Pride and Prejudice* (ids 1–2), *Dracula*, *Frankenstein*, … |
| US / UK retitles via `alt_titles` | *Philosopher’s Stone* ↔ *Sorcerer’s Stone*; *Northern Lights* ↔ *The Golden Compass* |
| Same title, different authors | *Foundation* (Asimov vs Ackroyd); *The Stranger* (Camus vs Coben); *Emma* (Austen vs McCall Smith) |
| Accent / transliteration variants | *Brontë* / *Bronte*; *García Márquez* / *Garcia Marquez*; Cyrillic / Spanish / Portuguese originals next to English |

Matcher tests (no network): `python manage.py test books.tests`.

## Key decisions and tradeoffs

| Decision | Tradeoff |
| --- | --- |
| COCO YOLO `book`, no training | Fast to ship; poor spine instance separation |
| Hosted VLM only on crops, not the full shelf | Lower cost / clearer per-spine JSON; depends on crop quality |
| OpenAI primary, Cursor automatic fallback | OpenAI is ~1 s/crop here; Cursor is ~1 min/crop when used |
| Sync `POST /api/photos/` | Simple for the exercise; HTTP request blocks for the whole pipeline |
| Auto-accept is suggestion-only until Review “Done” | Safer HITL; one more tap before library writes |
| Cap 8 VLM calls/photo | Keeps cost/latency bounded; ignores remaining detections |
| SQLite + no auth | Fine for a local demo; not multi-user |

## What’s unfinished / another day

Documented, not fixed after the deadline:

- **Detection quality** — still COCO boxes; a spine-trained detector or lightweight instance segmentation would cut clustered crops.
- **Unread detections** — boxes beyond the VLM cap never reach Review; no UI yet to “read more” or prioritize by confidence.
- **Sync API** — fine locally; production would queue detect/VLM and poll.
- **No auth / multi-user library / deploy** — out of scope for the take-home.
- **Cost not on the API payload** — tokens/cost are logged and summed by `bench_pipeline`, not stored on `ShelfPhoto`.
- **Catalog coverage** — real shelves often contain books absent from `catalog.csv`; those correctly fall to pending review / manual correct, not silent invent.
- **Original shelf photo** — processed from a temp upload; we keep crops for review, not a long-lived photo gallery.

With another day: spine-aware detector (or SAM-style refine), async jobs + progress events to the app, persist usage on the photo row, and a “load next N unread crops” control on Review.
