from datetime import datetime
from uuid import UUID

from typing import Literal
from pydantic import BaseModel, Field, field_validator

from schemas.architect_schema import ArchitectureDesign
from schemas.clarification_schema import ClarificationAnswer
from schemas.documentation_schema import Documentation
from schemas.requirement_schema import RequirementAnalysis
from schemas.research_schema import ResearchAnalysis
from schemas.sprint_schema import SprintPlan


class ProjectPlanRequest(BaseModel):
    project_idea: str = Field(
        min_length=1,
        max_length=10_000,
        description="A description of the software project to plan.",
    )
    clarifications: list[ClarificationAnswer] = Field(
        default_factory=list,
        max_length=3,
        description="Optional scope decisions confirmed by the user.",
    )
    source_ids: list[UUID] = Field(
        default_factory=list,
        max_length=20,
        description="Explicit knowledge sources used to ground the plan.",
    )

    @field_validator("project_idea")
    @classmethod
    def project_idea_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Project idea must not be blank.")
        return value


class ClarificationRequest(BaseModel):
    project_idea: str = Field(min_length=1, max_length=10_000)

    @field_validator("project_idea")
    @classmethod
    def project_idea_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Project idea must not be blank.")
        return value


class ProjectPlan(BaseModel):
    requirements: RequirementAnalysis
    research: ResearchAnalysis
    architecture: ArchitectureDesign
    sprint: SprintPlan
    documentation: Documentation


class KnowledgeSourceReference(BaseModel):
    document_id: UUID
    title: str
    source_type: Literal["upload", "project_plan"]


class KnowledgeSourceUploadResponse(KnowledgeSourceReference):
    chunk_count: int = Field(ge=1)


class ProjectPlanResponse(ProjectPlan):
    project_id: UUID
    created_at: datetime
    sources_used: list[KnowledgeSourceReference] = Field(default_factory=list)


class ProjectSummary(BaseModel):
    project_id: UUID
    project_idea: str
    created_at: datetime
