# AI usage

This take-home used AI assistance (Cursor) heavily for scaffolding, wiring, and iteration. Summary of model roles in the **product** itself:

## In-product models

| Role | Model / provider | Notes |
| --- | --- | --- |
| Book region detection | Ultralytics **YOLOv8n** (COCO pretrained, CPU) | No fine-tuning; weights downloaded locally on first run |
| Spine title/author OCR | **OpenAI `gpt-4o-mini`** vision (primary) | `detail=low`; parallel reads (≤3); 429 retries |
| Fallback spine read | **Cursor Cloud Agents** API | Used automatically if OpenAI fails / missing key; or `VLM_PROVIDER=cursor` |
| Catalog fuzzy match | **rapidfuzz** (local, not an LLM) | Title/author scoring + auto-accept / review thresholds |

## Prompts

Spine-read prompt lives in `backend/books/vlm.py` (`SPINE_PROMPT`): JSON-only `{title, author, confidence_note}`, no invented catalog matches.

## Cost / keys

- Keys live only in gitignored repo-root `.env` (`OPENAI_API_KEY`, optional `CURSOR_API_KEY`)  
- Never commit real keys; rotate any key that was pasted into chat  
- OpenAI usage is metered; Cursor fallback cost depends on your Cursor plan  

## What AI did *not* replace

Human review of matches (accept / correct / discard), catalog ambiguity design, and architecture tradeoffs documented in `README.md`.
