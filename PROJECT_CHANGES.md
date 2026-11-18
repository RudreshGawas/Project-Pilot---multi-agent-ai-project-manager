# Project Changes

This file summarizes the main features and improvements made to Project Pilot.

## Product and planning workflow

- Built a project-planning application that turns a user's project idea into:
  - Structured requirements and user stories
  - Technology and implementation research
  - System architecture and database design
  - A three-sprint plan and milestones
  - Project documentation, including an SRS, proposal, and README
- Orchestrated the planning stages with a LangGraph `StateGraph` and shared project state.
- Added a deterministic supervisor that routes to the next incomplete stage and stops the workflow when an agent fails.
- Added Pydantic schemas to validate structured outputs from planning agents.
- Added context builders so downstream agents receive relevant results from earlier stages.
- Updated agent prompts to keep plans aligned with the requested MVP, avoid adding unrequested features, and make assumptions explicit.

## User clarification

- Added an optional clarification step before planning.
- The API can generate up to three project-specific scope questions; users can answer, provide a custom answer, or skip them.
- Passes confirmed answers into the requirements stage so the rest of the plan reflects the user's choices.
- Clarification is an API step before the LangGraph workflow, not a LangGraph node.

## API, storage, and progress

- Added FastAPI endpoints to clarify project ideas, generate plans, stream plan progress, list saved projects, and retrieve a saved plan.
- Added PostgreSQL JSONB persistence for project plans.
- Added per-agent working, completed, and error progress events to the streaming workflow.
- Progress reports when an agent starts and finishes; it does not stream generated tokens.
- Added input validation and error handling for project requests and workflow failures.

## Frontend and exports

- Built a Next.js and React interface for submitting project ideas and viewing generated plans.
- Added agent progress indicators and compact, expandable agent-result cards with text previews.
- Organized results into readable sections to reduce long vertical scrolling.
- Added JSON download and a print-friendly layout that lets users save the plan as a PDF through the browser's print dialog.

## Development, deployment, and documentation

- Added Dockerfiles and Docker Compose configuration for running the frontend, backend, and PostgreSQL/pgvector together.
- Added GitHub Actions checks for backend tests, frontend production builds, and Docker Compose configuration.
- Added environment-variable examples and ignore rules to help keep local secrets out of version control.
- Documented setup, API endpoints, technologies, workflow behavior, and individual agent responsibilities in the README and `docs/agents.md`.

## RAG and retrieval

- Added document upload, text extraction, chunking, local embeddings, PostgreSQL/pgvector storage, and reranking.
- Supports PDF, Markdown, and plain-text sources.
- Added explicit source selection for requirements and architecture generation.
- Saved project plans can also be indexed as reference sources.
- Restricts retrieval to the document or saved-plan IDs selected for each request.

## Evaluation and observability

- Added a local RAGAS evaluation runner with a fixed 25-case synthetic benchmark.
- Added Faithfulness and Answer Relevancy measurements for vector-only and reranked retrieval.
- Added optional Langfuse tracing for workflow and RAG metadata; normal local runs do not require it.
- Documented evaluation commands and recorded one-run baseline and reranker comparison scores.

## Docker and local verification

- The complete local stack runs with Docker Compose.
- PostgreSQL/pgvector, FastEmbed cache, backend health checks, and frontend health checks are configured.
- The backend and frontend Docker images build successfully.
- The local Docker stack was started and verified manually, including application health and selected-source isolation.

## Testability improvement

- Changed Gemini client initialization to be lazy: importing the backend or constructing the service no longer requires a Gemini API key.
- The API key is still required when the app actually makes a Gemini request.
- Added tests to verify lazy initialization, client reuse, default model selection, and environment overrides.

## Important implementation notes

- The supervisor currently uses deterministic routing; it does not make a Gemini decision.
- RAG is optional. Requests without selected sources continue to use the existing planning workflow.
- The 25-case RAGAS results are verification and baseline measurements, not a claim that reranking improves every metric.
- Provider-backed evaluation and Langfuse usage are opt-in.
- Upload and API endpoints do not currently include authentication or per-user document ownership.
- Technology recommendations and generated sprint plans are proposals; they do not mean the recommended systems or tasks have been implemented.

## Recent GitHub commits

- `417d7f4` — Added the project-planning application, workflow, UI, documentation, and supporting infrastructure.
- `b831d51` — Initialized the Gemini client lazily so backend imports and tests do not require a real API key.


https://github.com/RudreshGawas/Project-Pilot---multi-agent-ai-project-manager