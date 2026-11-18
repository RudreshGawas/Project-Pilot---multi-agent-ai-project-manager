# RAG evaluation

The fixed golden set is in `backend/evals/data/questions.json` and uses the
synthetic, non-sensitive brief in
`backend/evals/data/cedar-loop-reference.md`. It contains 25 queries and
reference answers, including scope exclusions and questions the brief cannot
answer. Do not put user-uploaded or private plans in this dataset.

## Run locally

Requirements: a running local PostgreSQL instance using the Compose pgvector
image, backend plus optional evaluation dependencies, and a local Ollama
installation. Run these commands from the repository root; the generation and
embedding models run on the developer's machine:

```powershell
python -m pip install -r backend\requirements-eval.txt
ollama pull llama3.2
ollama pull nomic-embed-text
docker compose up -d db
$env:DATABASE_URL = "postgresql://project_manager:local_dev_only@localhost:5433/project_manager"
Set-Location backend
python -m evals.run_ragas --label vector-only --rerank off --output evals/results/vector-only.csv
python -m evals.run_ragas --label cross-encoder --rerank on --output evals/results/cross-encoder.csv
```

The Compose database is bound to loopback port `5433`. Set `DATABASE_URL`
explicitly for the evaluation process: the runner does not load `backend/.env`,
which may point at a hosted database. If you changed the Compose database
credentials, use the matching local URL here.

The runner indexes the fixed evaluation brief, retrieves excerpts with the
same production RAG code, generates answers with Ollama's local
OpenAI-compatible API, and runs RAGAS Faithfulness and AnswerRelevancy with the
same local evaluator. It removes its temporary vector-store record after the
run. No hosted judge or embedding API is called. Results are written to CSV;
the first invocation downloads local embedding/reranker models as needed.
RAGAS uses JSON-schema structured output for Ollama and rejects non-finite
metric scores instead of recording them as valid results.

Set `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, and `OLLAMA_EMBEDDING_MODEL` to use
different local Ollama settings. Change only one variable between comparable
runs. For a chunk-size experiment, use the same reranker and label both runs
with their chunk settings. The CLI's `--chunk-words` sets the ingestion chunk
size; the default overlap remains 40 words.

## Results log

These are one-run measurements on the fixed 25-case synthetic Cedar Loop
dataset, using Ollama `llama3.2`, `nomic-embed-text`, and RAGAS 0.4.4. They
verify the runner and are not evidence that reranking improves quality.

| Date | Experiment | Chunk words | Reranker | Faithfulness | Answer relevancy | Notes |
| --- | --- | ---: | --- | ---: | ---: | --- |
| 2026-11-17 | Vector-only baseline | 220 | Off | 0.666000 | 0.538853 | 25 cases; local Ollama |
| 2026-11-17 | Cross-encoder rerank | 220 | On | 0.662000 | 0.424201 | Same cases and model; relevancy was lower in this run |

## Optional Langfuse tracing

Normal requests and local RAGAS runs work without Langfuse credentials. To send
metadata-only traces to Langfuse Cloud, set `LANGFUSE_PUBLIC_KEY`,
`LANGFUSE_SECRET_KEY`, and `LANGFUSE_BASE_URL` in the local backend environment.
Traces include counts, source identifiers, experiment settings, and aggregate
scores; raw documents and excerpts are not included. Monitor the free-tier
quota and retention window before sharing the project publicly.
