# PPTX.AI — Native Presentation Design Engine Upgrade

**Status: engineering implementation completed for the features listed below; not certified as 9+/10 design quality or production-ready.**

## Audit: what needed fixing

The previous `backend/app/engine.py` always created the same title-and-bullet visual composition, with a header strip and up to six bullet paragraphs. Even chart/architecture/process material was not rendered as a chart or diagram. There was no intermediate visual specification or presentation-specific quality report. Generation validated only that the PPTX renderer returned bytes.

Core product flows were preserved: React/Vite interface, FastAPI routes, user auth, database tables, project blueprints, job queue, credits, versioning, theme identifiers, PPTX download and mobile control. **No database migration is required.** Extended visual fields live in the existing JSON `Presentation.slides` and `Version.slides` fields.

## What was implemented

- `backend/app/slide_spec.py`: Pydantic SlideSpec with 24 layout identifiers, legacy title/body/notes, key message, steps, metrics, sources, validated native chart data. Invalid and extreme values are rejected. All new fields are optional.
- `backend/app/design_planner.py`: deterministic content-aware layout inference, explicit design override support, and variation of repeated generic layouts.
- `backend/app/design_system.py`: complete, consistent midnight, light and aurora design tokens, including chart/text colors, panels, typography, spacing and contrast roles.
- `backend/app/engine.py`: refactored native PowerPoint renderer. Dedicated visual treatments and compatible variants include cover, section, conclusion, summary, text cards, two- and three-column comparisons, process, architecture, timelines, roadmaps, KPIs, reference lists and native bar/line/pie charts. Original narrative text is retained in slides or notes for constrained visual slides. The PowerPoint elements remain editable.
- `backend/app/intelligence.py`: reuse the current AI gateway with a validated richer slide schema and layout-planning instructions; no additional model provider and no invented evidence pipeline.
- `backend/app/quality.py`: structural geometry checking, conservative text-fit warnings, editable-element accounting, clear failure/warning status and optional independent LibreOffice PDF conversion.
- `backend/app/worker.py`: render and check output before committing versioned slides and settling credits. Critical geometry failures (and attempted but failed external PDF exports) fail and trigger existing credit refund handling. Quality summary attached to job result.
- `backend/app/main.py`: authenticated, rate-limited `GET /api/v1/presentations/{id}/quality`, preserving all existing routes and exports. Manual slide editor now accepts optional layout/chart/metrics metadata.
- `frontend/src/main.tsx` and `style.css`: quality report UI and optional slide layout selector. Editing title/body/notes preserves existing chart and design metadata instead of discarding it.
- Optional worker-only headless LibreOffice install path; off by default for smaller Docker images.

## New optional configuration

```dotenv
# Structural geometry validation is always active.
# For additional independent PDF reopen verification on every generated deck:
PPTX_VISUAL_QA=1
PPTX_INSTALL_RENDERING_QA=1
```

Set both for `docker compose build worker && docker compose up -d worker`, then verify image size, job latency and memory. For local development, install LibreOffice separately and set `PPTX_VISUAL_QA=1` for the worker. The API also checks geometry automatically; the API container requires LibreOffice independently if you explicitly enable PDF validation for its quality route. No additional LLM key is introduced. Without `LLM_API_KEY`, the existing editable outline-only mode remains, never simulated research.

## How to test

```bash
cd backend
python -m pytest -q
cd ..
python examples/make_quality_demo.py
python examples/benchmark_design_engine.py /path/to/PPTX_AI_Projects_Integrated_Full.zip
python examples/benchmark_suite.py
cd frontend
npm ci
npm run build
```

After signing in, create or open a presentation and use **Quality check** in the editing toolbar. For generated decks, check job `result.quality`. Manual presentation edits still produce versioned snapshots. Export and reopen with PowerPoint/LibreOffice before publication.

## Results measured in this environment

- Backend tests: **36 passed**.
- TSX syntax parse: **0 syntax errors**. Full frontend build **not performed**: `npm ci --offline` failed because `zustand@5.0.15` was missing from the npm cache.
- 15-slide *illustrative* demonstration: **15 pages independently converted to PDF by LibreOffice**, with zero critical geometry errors and six conservative text-fit warnings.
- Compared on the exact same illustrative 15-slide input:
  - Native editable charts: **0 → 3**.
  - Native connectors: **0 → 10**.
  - Distinct shape-sequence patterns: **1 → 11**.
  - Text elements: **37 → 136**.
  - Critical shape geometry errors: **0 → 0**.
  - LibreOffice PDF conversion: **passed → passed**.
- Coverage fixtures: **18** offline cases (six presentation categories × 5/10/20 slides), **0 critical geometry failures**. These use local draft outlines and do not test factual accuracy or original design creativity.

These numbers are **structural and mechanical measurements only**. Six new warnings result from conservative text-fit estimation, not verified clipping. The comparison is deliberately an illustrative engineering fixture, not a blind evaluation of AI-generated presentations. No assertion that visual quality is 9+/10 is warranted.

## Remaining work for a genuinely 9+/10-quality service

1. **Image intelligence**: licensed asset sourcing, optional AI image generation, crop/metadata/licensing pipeline, and visual grounding. Not implemented here.
2. **End-to-end visual review**: rendered screenshots and vision/human assessment, alignment and overlap checks that understand intended decoration, followed by targeted correction and bounded re-render loops. PDF page-count checking is implemented, but not an aesthetic/vision model.
3. **Editable diagrams beyond the current flow/architecture primitives**: full ERDs, sophisticated swimlanes, advanced mathematical formulas and native tables.
4. **Content/evidence verification**: real research-backed citations, numerical provenance and quality assessment of model output. Prompting against fabrication alone cannot guarantee factual correctness.
5. **Reference-based style extraction** from uploaded PPTX, true slide masters, animation directives and broad font-substitution testing.
6. **Operational testing**: real LLM credentials, concurrency/latency/cost benchmarking, Docker-based PostgreSQL/Redis integration, CI frontend build, actual Microsoft PowerPoint rendering and production deployment.
7. **Human evaluation**: blinded ratings from different users across the six target domains, followed by iteration. Automated geometry scores are not artistic quality ratings.

## Compatibility and safe merge

Copy the changed/additional files from the provided patch into a working branch. Retain existing database and API configuration, make a backup of any production data, run the suite and build before deployment, and merge only after inspecting the file diffs. All existing API URLs and prices remain unchanged. This package does not update GitHub or deploy services automatically.
