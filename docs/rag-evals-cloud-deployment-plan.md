# Project Pilot: RAG, evaluations, and cloud deployment plan

**Status:** Approved for implementation with a free-tier-only constraint
**Prepared:** 2026-11-17

## Goal and current baseline

Extend the existing FastAPI, LangGraph, Next.js, and PostgreSQL application so
users can ground project requirements and architecture in selected reference
documents, measure retrieval quality, inspect traces, and deploy the app.

The app already saves plans in PostgreSQL JSONB and has local Docker Compose and
GitHub Actions checks. `backend/rag/` contains empty module placeholders, but
there is no active document-ingestion or retrieval path, vector extension,
evaluation suite, or image-publishing workflow. The current workflow generates
requirements first and architecture after research; the requirement node uses
its prompt directly, while the architecture node uses the shared context
builder.

## Proposed architecture

```text
Next.js document picker ── upload/select ──> FastAPI knowledge API
                                                │
                                      extract → chunk → embed
                                                │
                                     PostgreSQL + pgvector
                                                │
New plan request + selected source IDs ──> LangGraph
                                            ├─ retrieve/rerank → Requirements
                                            └─ retrieve/rerank → Architecture
                                                │
                                      response with source references
                                                │
                                  RAGAS evaluation / Langfuse traces
```

PostgreSQL remains the only application database. Generated plans continue to
use the existing `projects` table. A separate vector database is not proposed.

## Milestone 1 — PostgreSQL-backed RAG

### What changes and where

| Area | Proposed location | Change |
| --- | --- | --- |
| Storage | `docker-compose.yml`, `backend/rag/vectorstore.py` | Use a PostgreSQL 17 image that provides pgvector; lazily enable the `vector` extension and create idempotent document/chunk tables and a cosine HNSW index. Preserve the existing PostgreSQL volume and project records. |
| Ingestion and retrieval | `backend/rag/embeddings.py`, `retriever.py`, `vectorstore.py` | Implement text extraction, chunking with overlap, configurable embeddings, pgvector writes/search, and a reranking stage. Keep database and embedding access behind these modules. |
| Persistence | `backend/services/` and a migration/schema file | Store document metadata and chunk text, provenance, embedding model/version, and vector values. Make ingestion repeatable and allow document deletion to remove its chunks. |
| API | `backend/main.py`, `backend/schemas/` | Add document upload/list/delete endpoints and accept explicitly selected document or saved-plan source IDs on plan requests. Return source metadata with generated results. |
| Agent workflow | `backend/graph/state.py`, `backend/graph/workflow.py`, `backend/agents/requirement/node.py`, `backend/utils/context_builder.py`, architecture prompt/schema | Retrieve context before requirements and again before architecture; pass only the relevant, ranked excerpts to each agent and require source references for claims grounded in those excerpts. Requests without sources retain current behavior. |
| UI | `frontend/app/page.js` and related frontend styles/components | Add document upload and source selection near project planning, allow selection of previously saved plans, and show source references in the generated requirements and architecture. |
| Configuration and tests | `backend/.env.example`, backend tests | Document embedding/model settings and add mocked unit/API tests plus PostgreSQL integration coverage for extension setup, isolation by selected source IDs, and retrieval ordering. |

### How it works

1. A user uploads supported documents (initial proposal: PDF, Markdown, and
   plain text) or selects a previously generated plan. The API extracts text
   and records source metadata.
2. The ingestion service normalizes text, splits it into overlapping chunks,
   requests embeddings from a configurable provider, and stores chunks and
   vectors in PostgreSQL. The embedding model and vector dimension are recorded
   so incompatible model changes cannot silently mix vectors.
3. Before the requirements and architecture agents run, the retriever embeds
   the relevant query/context, searches only the sources selected for that
   request, fetches a larger candidate set, and reranks the candidates. The
   agents receive a small, bounded set of excerpts with source IDs/titles.
4. The generated plan remains in the current response shape, with additive
   source references for grounded content. If no sources are selected, the
   existing planning path is preserved.

Use local FastEmbed models for embeddings and a small cross-encoder reranker so
document content and queries are not sent to an additional hosted model API.
Both models download once and run locally; the first download and CPU/memory
requirements should be documented. Chunk size, overlap, initial top-k, final
context count, and file size/type limits will be configuration choices
validated during the first milestone and recorded with evaluation runs. The
vector-only path remains the comparison baseline.

### Data access and upload safety

The repository currently has no user authentication or ownership model. The
proposal therefore avoids searching an implicit global corpus: each plan
request must name the source IDs it is permitted to use, and results identify
their source. This is not a substitute for authorization. Until authentication
and ownership are implemented, cloud upload/API access should remain private or
restricted to a controlled demo; do not expose anonymous document uploads.
Enforce upload size/type limits, reject unsupported files explicitly, and do
not persist raw upload files unless later required.

## Milestone 2 — Evaluation and observability

### What changes and where

| Area | Proposed location | Change |
| --- | --- | --- |
| Golden set | `backend/evals/` | Add 20–30 curated question/corpus cases with expected answer facts and relevant source/chunk IDs. Use synthetic or public material, not private user uploads. |
| Runner | `backend/evals/` and a small CLI entry point | Run the same corpus against fixed settings and save machine-readable scores plus a human-readable comparison table. |
| Metrics/results | `docs/evals/` | Record faithfulness and answer relevancy with RAGAS, plus retrieval context precision/recall where the dataset supports them. Record model, chunking, top-k, reranker, run date, and baseline/variant scores. |
| Tracing | `backend/services/` or a focused observability module | Add optional Langfuse traces/spans around workflow agents, retrieval, reranking, and evaluation calls. Configure through environment variables; never require Langfuse for normal local tests. |
| CI | `.github/workflows/ci.yml` | Run fast deterministic eval/unit checks in CI. Keep provider-backed RAGAS runs opt-in so CI needs no API keys and is not billed unexpectedly. |

### How it works

Create a small fixed dataset that tests lookup, paraphrase, multi-source
synthesis, conflicting or missing evidence, and questions that should not be
answered from the supplied corpus. Run a baseline with vector retrieval only.
Then change one variable at a time (for example chunk size, top-k, or
reranking), rerun the identical cases, and record before/after scores and
latency. Do not claim improvement until measured; include unsuccessful
experiments as well as successful ones. Run RAGAS with a local Ollama model by
default; do not make a hosted model call from the evaluation runner.

Langfuse should receive trace/span identifiers, model and retrieval
configuration, source IDs, ranks/scores, token/latency metadata, and evaluation
scores. Do not send full uploaded documents or sensitive excerpts by default;
redaction and sampling should be configurable. Keep API keys in local
environment files or deployment secrets, never in the repository.

## Milestone 3 — Cloud deployment

### Recommended first deployment

Candidate deployment: **AWS ECR + ECS on Fargate + RDS for PostgreSQL, with the
Next.js frontend on Vercel**. This fits the existing Dockerized API and database,
but it is not guaranteed to be free. Build and validate the images and
deployment configuration locally/within CI first. Do not create AWS/Vercel
resources or publish images until the account's free-tier eligibility and
expected charges are verified and the user separately confirms provisioning.
RDS must use a PostgreSQL version/extension combination verified to support
pgvector.

An Azure Container Apps deployment is an alternative if the user prefers Azure.
The exact managed PostgreSQL option, pgvector support, networking, secrets, and
pricing would then be re-evaluated before implementation. This proposal does not
include provisioning either cloud account or service.

### What changes and where

| Area | Proposed location | Change |
| --- | --- | --- |
| Image CI | `.github/workflows/ci.yml` or a dedicated deployment workflow | Build the backend and frontend images on pushes/PRs without publishing. Add a separately gated publish/deploy workflow only after the user verifies free-tier eligibility and explicitly approves resource creation. |
| Cloud configuration | `deploy/` or infrastructure configuration selected at approval | Define ECS service/task, health checks, RDS connectivity, environment/secrets, and frontend origin without committing credentials. |
| Database | PostgreSQL migration/setup scripts | Apply schema and pgvector extension setup to the managed database; configure backups and a private network path from ECS. |
| Frontend | Vercel project settings and frontend environment | Set the production API URL, allowed origin, and deployment branch; retain the existing Next.js build. |
| Operations | deployment documentation and CI environment settings | Add release/rollback steps, health verification, log inspection, cost alerts, and a documented teardown procedure for the demo environment. |

If deployment is later approved, use GitHub Actions OIDC/federated identity
instead of long-lived AWS access keys where repository configuration permits.
Keep the database private, require TLS for public endpoints, store secrets in
the cloud secret manager, and do not publish production deployment credentials
to pull-request jobs. Keep the first deployment restricted until authentication
and per-user document ownership are decided.

### Current pricing/free-tier check

Checked **2026-11-17** against the official pages below. Limits and eligibility
vary by account age, region, account plan, and service configuration; this is a
planning check, not a cost quote or guarantee of a zero-cost deployment.

- AWS currently advertises up to **$200 in credits over six months** for new
  accounts, with different Free and Paid account-plan restrictions. Do not
  assume every service is available on the Free plan.
- ECR's page lists **500 MB/month** of private-repository storage for one year
  for new customers; storage and data transfer can be billed outside eligible
  limits.
- ECS has no separate orchestration charge, but Fargate compute and its
  supporting resources are billed. A continuously running API is not inherently
  free.
- The RDS PostgreSQL page lists a new-customer offer for selected Single-AZ
  instances and storage for one year. Confirm that the chosen account plan,
  engine, region, and instance qualify; a managed database can incur ongoing
  costs.
- Vercel currently lists a **$0/month Hobby plan** with usage limits. Confirm
  that its current terms suit the intended use before connecting a public app.
- Langfuse Cloud currently lists a free Hobby tier with **50,000 units/month,
  30 days of data access, and two users**. Usage beyond the tier or retention
  requirements may require a paid plan.

Before proposing deployment, enter the selected region and expected always-on
hours/storage/data transfer into the AWS Pricing Calculator, set a billing
budget/alert, check the account's Free Tier eligibility, and explicitly approve
provisioning. No deployment step should enable paid overages. Credits are not a
spending cap on every account plan.
Delete test resources when finished; stop/scale down compute where possible,
but do not assume stopping a service stops database, storage, networking, or
logging charges.

Official references:

- [AWS Free Tier](https://aws.amazon.com/free/)
- [Amazon ECR pricing](https://aws.amazon.com/ecr/pricing/)
- [Amazon ECS pricing](https://aws.amazon.com/ecs/pricing/)
- [Amazon RDS for PostgreSQL pricing](https://aws.amazon.com/rds/postgresql/pricing/)
- [Vercel pricing](https://vercel.com/pricing)
- [Langfuse pricing](https://langfuse.com/pricing)
- [pgvector](https://github.com/pgvector/pgvector)

## Delivery order and acceptance checks

1. **RAG:** Upload/index a supported document and retrieve its relevant chunk
   for the requirements and architecture stages; confirm an unselected
   document is never returned; confirm no-source requests still pass the
   existing workflow tests; verify persistence after container restart.
2. **Evals/observability:** Run all 20–30 golden cases, produce baseline and
   one-variable comparison scores, and inspect a Langfuse trace without
   exposing raw document content. Clearly label any provider-backed eval as
   opt-in.
3. **Cloud preparation:** Build the images in CI, validate deployment settings,
   and document health checks, rollback, and teardown. Publishing or launching
   cloud resources is deferred until the account's free eligibility is
   confirmed and provisioning is separately approved.

Existing API, workflow, repository, frontend build, and Docker Compose checks
remain in place. Add focused tests for new ingestion/retrieval behavior and
configuration; run provider-backed evaluations separately from deterministic
CI.

## Implementation scope after approval

Approved defaults and constraints:

1. Proceed in the three milestones in this document, keeping RAG optional for
   requests without selected sources.
2. Use AWS ECR/ECS Fargate/RDS plus Vercel unless Azure is preferred.
3. Start with a private/restricted demo; defer public uploads until an
   authentication and ownership approach is approved.
4. Begin with PDF, Markdown, and plain-text uploads; use local FastEmbed
   embeddings and reranking. The existing Gemini generation path is unchanged.
5. Use local Ollama for RAGAS metrics. Langfuse is opt-in and may be configured
   on its free tier with content redaction.
6. Restrict cloud work to building/testing images and preparing configuration.
   Do not provision resources, publish to a paid service, or enable paid
   overages until free eligibility is verified and provisioning is separately
   approved.

Cloud resource creation and any spend remain a separate explicit confirmation
step.
