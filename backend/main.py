import json
import logging
import os
from uuid import UUID

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pypdf.errors import PdfReadError

from graph.workflow import graph, progress_graph
from prompts.clarification_prompt import get_clarification_prompt
from schemas.api_schema import (
    ClarificationRequest,
    KnowledgeSourceReference,
    KnowledgeSourceUploadResponse,
    ProjectPlan,
    ProjectPlanRequest,
    ProjectPlanResponse,
    ProjectSummary,
)
from schemas.clarification_schema import ClarificationResponse
from services import project_repository
from services.llm_service import llm_service
from services.observability import observe
from rag.retriever import (
    ensure_source_indexed,
    extract_document_text,
    ingest_document,
)
from rag.vectorstore import delete_document, list_documents


logger = logging.getLogger(__name__)
PLAN_OUTPUT_KEYS = (
    "requirements",
    "research",
    "architecture",
    "sprint",
    "documentation",
)
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

app = FastAPI(
    title="Multi-Agent AI Project Manager",
    description="Generate structured project plans from a software idea.",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv(
            "FRONTEND_ORIGINS", "http://localhost:3000"
        ).split(",")
        if origin.strip()
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


def _validate_plan_result(result: dict) -> ProjectPlan:
    if result.get("error") is not None:
        logger.error("Project planning workflow failed: %s", result["error"])
        raise HTTPException(
            status_code=502,
            detail="Project planning failed while generating the plan. Please retry.",
        )

    missing_outputs = [key for key in PLAN_OUTPUT_KEYS if result.get(key) is None]
    if missing_outputs:
        logger.error(
            "Project planning workflow completed without outputs: %s",
            ", ".join(missing_outputs),
        )
        raise HTTPException(
            status_code=502,
            detail="Project planning did not generate a complete plan. Please retry.",
        )

    try:
        return ProjectPlan.model_validate(
            {key: result[key] for key in PLAN_OUTPUT_KEYS}
        )
    except Exception as error:
        logger.exception("Project planning workflow returned invalid output.")
        raise HTTPException(
            status_code=502,
            detail="Project planning returned an invalid plan. Please retry.",
        ) from error


def _save_project_plan(project_idea: str, result: dict) -> ProjectPlanResponse:
    plan = _validate_plan_result(result)
    sources_used = [
        KnowledgeSourceReference.model_validate(source)
        for source in result.get("retrieved_sources", [])
    ]
    saved_plan = plan.model_dump(mode="json")
    saved_plan["sources_used"] = [
        source.model_dump(mode="json") for source in sources_used
    ]
    try:
        saved_project = project_repository.save_project(
            project_idea=project_idea,
            plan=saved_plan,
        )
    except Exception as error:
        logger.exception("Could not persist the generated project plan.")
        raise HTTPException(
            status_code=503,
            detail="The project plan was generated but could not be saved.",
        ) from error

    return ProjectPlanResponse(
        project_id=saved_project["project_id"],
        created_at=saved_project["created_at"],
        sources_used=sources_used,
        **plan.model_dump(),
    )


def _server_event(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


def _project_input_with_clarifications(request: ProjectPlanRequest) -> str:
    if not request.clarifications:
        return request.project_idea

    choices = "\n".join(
        f"- {answer.question}: {answer.answer}"
        for answer in request.clarifications
    )
    return (
        f"{request.project_idea}\n\n"
        "User-confirmed scope choices (treat these as requirements):\n"
        f"{choices}"
    )


def _initial_workflow_state(request: ProjectPlanRequest) -> dict:
    for source_id in request.source_ids:
        try:
            ensure_source_indexed(source_id)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except Exception as error:
            logger.exception("Could not prepare knowledge source %s.", source_id)
            raise HTTPException(
                status_code=503,
                detail="A selected knowledge source could not be indexed.",
            ) from error

    return {
        "user_input": _project_input_with_clarifications(request),
        "requirements": None,
        "research": None,
        "architecture": None,
        "sprint": None,
        "documentation": None,
        "supervisor_decision": None,
        "current_node": None,
        "status": None,
        "error": None,
        "source_ids": request.source_ids,
        "retrieved_sources": [],
    }


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/api/v1/knowledge/documents",
    response_model=KnowledgeSourceUploadResponse,
    status_code=201,
)
async def upload_knowledge_document(
    file: UploadFile = File(...),
) -> KnowledgeSourceUploadResponse:
    try:
        filename = file.filename or ""
        if not filename.lower().endswith((".pdf", ".md", ".txt")):
            raise HTTPException(
                status_code=415,
                detail="Only PDF, Markdown, and plain-text files are supported.",
            )

        content = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=413,
                detail="The upload exceeds the 10 MB limit.",
            )

        text = extract_document_text(filename, content)
        indexed = ingest_document(title=filename, text=text)
    except HTTPException:
        raise
    except (ValueError, UnicodeDecodeError, PdfReadError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        logger.exception("Could not index uploaded document %s.", filename)
        raise HTTPException(
            status_code=503,
            detail="The document could not be indexed. Check database and local model availability.",
        ) from error
    finally:
        await file.close()

    return KnowledgeSourceUploadResponse.model_validate(indexed)


@app.delete(
    "/api/v1/knowledge/documents/{document_id}",
    status_code=204,
)
def remove_knowledge_document(document_id: UUID) -> Response:
    try:
        deleted = delete_document(document_id)
    except Exception as error:
        logger.exception("Could not delete knowledge source %s.", document_id)
        raise HTTPException(
            status_code=503,
            detail="The knowledge source could not be deleted.",
        ) from error
    if not deleted:
        raise HTTPException(status_code=404, detail="Knowledge source not found.")
    return Response(status_code=204)


@app.get(
    "/api/v1/knowledge/documents",
    response_model=list[KnowledgeSourceUploadResponse],
)
def get_knowledge_documents(
    limit: int = Query(default=100, ge=1, le=500),
) -> list[KnowledgeSourceUploadResponse]:
    try:
        documents = list_documents(limit=limit)
    except Exception as error:
        logger.exception("Could not list knowledge sources.")
        raise HTTPException(
            status_code=503,
            detail="Knowledge sources are currently unavailable.",
        ) from error
    return [
        KnowledgeSourceUploadResponse.model_validate(document)
        for document in documents
    ]


@app.post(
    "/api/v1/projects/clarify",
    response_model=ClarificationResponse,
)
def clarify_project_idea(request: ClarificationRequest) -> ClarificationResponse:
    try:
        structured_llm = llm_service.get_structured_llm(ClarificationResponse)
        questions = structured_llm.invoke(
            get_clarification_prompt(request.project_idea)
        )
        return ClarificationResponse.model_validate(questions)
    except Exception as error:
        logger.exception("Could not generate project clarification questions.")
        raise HTTPException(
            status_code=502,
            detail="Could not prepare project questions. Please retry.",
        ) from error


@app.post("/api/v1/projects/plan/stream")
def create_project_plan_stream(request: ProjectPlanRequest) -> StreamingResponse:
    try:
        project_repository.check_database_connection()
    except Exception as error:
        logger.exception("Database preflight check failed before project planning.")
        raise HTTPException(
            status_code=503,
            detail="Project storage is unavailable. Check DATABASE_URL and retry.",
        ) from error

    initial_state = _initial_workflow_state(request)

    def stream_events():
        result = {}
        try:
            with observe(
                "project.plan",
                {"has_sources": bool(request.source_ids), "source_count": len(request.source_ids)},
            ) as observation:
                for mode, chunk in progress_graph.stream(
                    initial_state,
                    stream_mode=["custom", "values"],
                ):
                    if mode == "custom":
                        yield _server_event({"type": "progress", **chunk})
                    elif mode == "values":
                        result = chunk
                if observation is not None:
                    observation.update(output={"completed": result.get("error") is None})

            plan = _save_project_plan(request.project_idea, result)
            yield _server_event(
                {"type": "complete", "plan": plan.model_dump(mode="json")}
            )
        except HTTPException as error:
            yield _server_event({"type": "error", "message": error.detail})
        except Exception:
            logger.exception("Streaming project planning workflow failed.")
            yield _server_event(
                {
                    "type": "error",
                    "message": "Project planning failed due to an internal error.",
                }
            )

    return StreamingResponse(
        stream_events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post(
    "/api/v1/projects/plan",
    response_model=ProjectPlanResponse,
)
def create_project_plan(request: ProjectPlanRequest) -> ProjectPlanResponse:
    try:
        project_repository.check_database_connection()
    except Exception as error:
        logger.exception("Database preflight check failed before project planning.")
        raise HTTPException(
            status_code=503,
            detail="Project storage is unavailable. Check DATABASE_URL and retry.",
        ) from error

    initial_state = _initial_workflow_state(request)

    try:
        with observe(
            "project.plan",
            {"has_sources": bool(request.source_ids), "source_count": len(request.source_ids)},
        ) as observation:
            result = graph.invoke(initial_state)
            if observation is not None:
                observation.update(output={"completed": result.get("error") is None})
    except Exception as error:
        logger.exception("Project planning workflow raised an exception.")
        raise HTTPException(
            status_code=500,
            detail="Project planning failed due to an internal error.",
        ) from error

    return _save_project_plan(request.project_idea, result)


@app.get(
    "/api/v1/projects",
    response_model=list[ProjectSummary],
)
def list_project_plans(
    limit: int = Query(default=20, ge=1, le=100),
) -> list[ProjectSummary]:
    try:
        projects = project_repository.list_projects(limit=limit)
    except Exception as error:
        logger.exception("Could not list saved projects.")
        raise HTTPException(
            status_code=503,
            detail="Project storage is currently unavailable.",
        ) from error

    return [ProjectSummary.model_validate(project) for project in projects]


@app.get(
    "/api/v1/projects/{project_id}",
    response_model=ProjectPlanResponse,
)
def get_project_plan(project_id: UUID) -> ProjectPlanResponse:
    try:
        project = project_repository.get_project(project_id)
    except Exception as error:
        logger.exception("Could not retrieve project %s.", project_id)
        raise HTTPException(
            status_code=503,
            detail="Project storage is currently unavailable.",
        ) from error

    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")

    return ProjectPlanResponse.model_validate(project)