# LexQuest Original Content Pack

This archive is compiled as a compact set of source materials for external audit and preparation of text about the project.

Left inside:
- source code of the application backend (`backend/app`);
- frontend source code (`frontend/src`);
- database migrations and tests;
- workflow-configuration and text templates related to generation;
- several markdown documents that explain the product logic and pipeline design.

Specifically excluded:
- `node_modules`, `.venv`, `dist`, `build`, `__pycache__`, `.pyc`;
- databases, logs, temporary files, binary artifacts;
- images, audio, archives, large `.docx`, backups and service dumps;
- a typical infrastructure connection, if it does not help to understand the product itself.

Brief content map:
- `backend/app` - FastAPI backend, domain models, services, API routes, integration with LLM/ComfyUI/TTS.
- `backend/alembic_migrations` - evolution of the project data schema.
- `backend/tests` - tests of key API and service layer scenarios.
- `frontend/src` - React/TypeScript interface of the project, editors, world library, player, voice and generative screens.
- `tools/workflows` and `tools/comfyui_wildcards` - configs and text building blocks for generative workflows.
- `docs` and root `.md` - explanations on creative mode, quest authoring, pipeline profiles and parameter flow.

If you read the package as material for text, a reasonable order is:
1. `docs/CREATIVE_MODE_GUIDE_RU.md`
2. `docs/QUEST_AUTHORING_GUIDE_RU.md`
3. `frontend/README.md`
4. `backend/app/main.py`
5. `backend/app/services/wizard.py`
6. `backend/app/services/narrative_ai.py`
7. `docs/PIPELINE_PROFILE.md`
8. `docs/WORKFLOW_PARAMETER_FLOW.md`
9. `GENERATION_FLOW.md`
10. `WORKFLOWS.md`

Note on the archive:
- There may be links to images in markdown files that are deliberately not included to keep the package lightweight.
