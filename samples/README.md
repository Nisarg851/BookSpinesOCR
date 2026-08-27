# Sample bookshelf photos for local detection / pipeline tests.

Tracked images (used by `bench_pipeline`):

- `bookshelf.jpg` — dense shelf (many COCO boxes)
- `Good-Book-Spines.jpg`
- `Room40B.jpg`
- `book-spine.jpg.webp`

```powershell
# from repo root, venv active, OPENAI_API_KEY set
python backend\manage.py bench_pipeline
python backend\manage.py detect_spines samples\bookshelf.jpg
```
