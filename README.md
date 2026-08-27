# Shelfie

Photo of a bookshelf → structured personal library.

This is a local-only take-home: Expo (React Native) client + Django REST API. No deployment.

## Status

Phase 0 scaffolding only. The app and API boot, and the client can reach `GET /api/health/`. Spine detection, VLM reads, catalog matching, and library UI are not built yet.

## Stack (local vs hosted)

| Piece | Where it runs |
| --- | --- |
| Spine detection (pretrained, CPU) | Local (not wired yet) |
| Title/author read from spine crops | Hosted VLM (not wired yet; provider TBD) |
| Catalog match + library | Local SQLite (not wired yet) |

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

`load_catalog` upserts from repo-root `catalog.csv` (safe to re-run). Health check: `http://127.0.0.1:8000/api/health/` → `{"status":"ok","service":"shelfie"}`

`0.0.0.0` is required so a physical phone on the same LAN can reach the API. Simulators can use localhost / `10.0.2.2`.

### Mobile (Expo)

```powershell
cd mobile
npm install
npx expo start
```

Then open in Expo Go, an iOS simulator, or an Android emulator.

Default API URLs:

- iOS simulator / Expo web: `http://127.0.0.1:8000`
- Android emulator: `http://10.0.2.2:8000`

On a **physical device**, localhost is the phone. Create `mobile/.env` (see `mobile/.env.example`) with your computer's LAN IP:

```
EXPO_PUBLIC_API_URL=http://192.168.x.x:8000
```

Restart Expo after changing `.env`.

## Catalog

`catalog.csv` has ~130 books with deliberate ambiguities (duplicate editions, US/UK titles, shared titles, omnibus vs volumes, substring titles, author-name variants). Load into SQLite with `python manage.py load_catalog`.

## Measured latency / cost

Not applicable yet (no detection or VLM calls).

## What's unfinished

Everything past scaffolding: detection, VLM, matching, review screen, library persistence, tests, photos, full README.
