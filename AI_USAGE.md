## Tools used while building

| Tool | Role |
| --- | --- |
| **Cursor** (Agent / Composer in the IDE) | Most of the scaffolding and iteration: Django app layout, Expo screens, API wiring, matcher tests, README/bench command, debugging timeouts and provider switches |
| **OpenAI `gpt-4o-mini` (vision)** | **In-product** spine title/author reader (primary VLM). Also the source of measured token usage for cost estimates |
| **Cursor Cloud Agents API** | **In-product** automatic VLM fallback when OpenAI fails / key missing (or `VLM_PROVIDER=cursor`). Earlier in the project this was the primary reader before OpenAI was wired |
| **Ultralytics YOLOv8n** | **In-product** local detector — pretrained COCO weights, no fine-tuning, not “prompted” |

No other coding AIs were used as a separate workflow (no ChatGPT-web paste loop, no Copilot-as-primary). Human decisions covered catalog ambiguity design, HITL flow, provider choice, and what to leave unfinished.

## Roughly where AI help showed up

- Backend: `detection.py`, `vlm.py`, `matching.py`, `pipeline.py`, DRF views/serializers, management commands (`bench_pipeline`, etc.)
- Mobile: Capture / Review / Library screens, upload helpers, navigation
- Docs: README structure and this file (numbers in the latency table are from a real `bench_pipeline` run, not invented by the model)

Prompts for the product VLM live in `backend/books/vlm.py` (`SPINE_PROMPT`).

