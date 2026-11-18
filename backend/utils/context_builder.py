from graph.state import ProjectState
from rag.retriever import retrieve_context


class ContextBuilder:
    """
    Responsible for extracting only the data required by each agent
    from the shared ProjectState.
    """

    def __init__(self, state: ProjectState):
        self.state = state

    def build_research_context(self) -> dict:
        """
        Build the context required by the Research Agent.
        """

        requirements = self.state.get("requirements")

        if requirements is None:
            raise ValueError(
                "RequirementAnalysis not found. Research Agent requires completed requirements."
            )

        return {
            "functional_requirements": requirements.functional_requirements,
            "non_functional_requirements": requirements.non_functional_requirements,
        }

    def build_architect_context(self) -> dict:
        """
        Build the context required by the Architect Agent.
        """

        requirements = self.state.get("requirements")
        research = self.state.get("research")

        if requirements is None:
            raise ValueError(
                "RequirementAnalysis not found. Architect Agent requires completed requirements."
            )

        if research is None:
            raise ValueError(
                "ResearchAnalysis not found. Architect Agent requires completed research."
            )

        source_ids = self.state.get("source_ids", [])
        retrieved = retrieve_context(
            source_ids,
            " ".join(
                [
                    *requirements.functional_requirements,
                    *requirements.non_functional_requirements,
                    *research.best_practices,
                ]
            ),
        )
        self._merge_retrieved_sources(retrieved["sources"])

        return {
            "functional_requirements": requirements.functional_requirements,
            "non_functional_requirements": requirements.non_functional_requirements,
            "research": research,
            "retrieved_context": retrieved["context"],
        }

    def _merge_retrieved_sources(self, sources: list[dict]) -> None:
        by_id = {
            source["document_id"]: source
            for source in self.state.get("retrieved_sources", [])
        }
        by_id.update({source["document_id"]: source for source in sources})
        self.state["retrieved_sources"] = list(by_id.values())

    def build_sprint_context(self) -> dict:
        """
        Build the context required by the Sprint Planning Agent.
        """

        requirements = self.state.get("requirements")
        research = self.state.get("research")
        architecture = self.state.get("architecture")

        if requirements is None:
            raise ValueError(
                "RequirementAnalysis not found. Sprint Agent requires completed requirements."
            )

        if research is None:
            raise ValueError(
                "ResearchAnalysis not found. Sprint Agent requires completed research."
            )

        if architecture is None:
            raise ValueError(
                "ArchitectureDesign not found. Sprint Agent requires completed architecture."
            )

        return {
            "requirements": requirements,
            "research": research,
            "architecture": architecture,
        }

    def build_documentation_context(self) -> dict:
        """
        Build the context required by the Documentation Agent.
        """

        requirements = self.state.get("requirements")
        research = self.state.get("research")
        architecture = self.state.get("architecture")
        sprint = self.state.get("sprint")

        if requirements is None:
            raise ValueError(
                "RequirementAnalysis not found. Documentation Agent requires completed requirements."
            )

        if research is None:
            raise ValueError(
                "ResearchAnalysis not found. Documentation Agent requires completed research."
            )

        if architecture is None:
            raise ValueError(
                "ArchitectureDesign not found. Documentation Agent requires completed architecture."
            )

        if sprint is None:
            raise ValueError(
                "SprintPlan not found. Documentation Agent requires completed sprint planning."
            )

        return {
            "requirements": requirements,
            "research": research,
            "architecture": architecture,
            "sprint": sprint,
        }