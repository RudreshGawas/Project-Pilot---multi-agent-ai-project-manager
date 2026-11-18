# agents/requirement/node.py

from graph.state import ProjectState
from prompts.requirement_prompt import get_requirement_prompt
from rag.retriever import retrieve_context
from schemas.requirement_schema import RequirementAnalysis
from services.llm_service import llm_service
from services.observability import observe


def requirement_node(state: ProjectState) -> ProjectState:
    try:
        structured_llm = llm_service.get_structured_llm(RequirementAnalysis)
        retrieved = retrieve_context(
            state.get("source_ids", []),
            state["user_input"],
        )
        sources = {
            source["document_id"]: source
            for source in state.get("retrieved_sources", [])
        }
        sources.update(
            {source["document_id"]: source for source in retrieved["sources"]}
        )
        state["retrieved_sources"] = list(sources.values())
        prompt = get_requirement_prompt(
            state["user_input"],
            retrieved_context=retrieved["context"],
        )
        with observe(
            "agent.generate",
            {
                "agent": "Requirement Agent",
                "has_retrieval": bool(retrieved["context"]),
            },
        ) as observation:
            result = structured_llm.invoke(prompt)
            if observation is not None:
                observation.update(output={"completed": True})

        state["requirements"] = result
        state["current_node"] = "Requirement Node"
        state["status"] = "Completed"

    except Exception as e:
        state["error"] = f"Requirement Agent failed: {e}"
        state["status"] = "Error"

    return state
