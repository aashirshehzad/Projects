"""
LangGraph workflow definition for the stock-analysis pipeline.

Currently wires a single node (Agent 1 – quantitative).
Future agents will be appended as additional nodes.
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.agent_quantitative import quantitative_agent
from app.state import StockAnalysisState


def build_graph() -> StateGraph:
    """
    Construct and compile the LangGraph workflow.

    Topology (current)
    ──────────────────
        START → quantitative_agent → END

    Returns
    -------
    CompiledGraph
        A compiled LangGraph graph ready for ``.invoke()``.
    """
    # LangGraph requires a TypedDict or dict-style state for its internal
    # reducer logic.  We bridge Pydantic ↔ dict at the graph boundary.
    workflow = StateGraph(dict)

    # ── nodes ────────────────────────────────────────────────────────────
    def _quant_node(state_dict: dict) -> dict:
        """Wrap the Pydantic-based agent so it integrates with LangGraph's dict state."""
        incoming = StockAnalysisState(**state_dict)
        result = quantitative_agent(incoming)
        return result.model_dump()

    workflow.add_node("quantitative_agent", _quant_node)

    # ── edges ────────────────────────────────────────────────────────────
    workflow.set_entry_point("quantitative_agent")
    workflow.add_edge("quantitative_agent", END)

    return workflow.compile()


# Pre-built graph instance for import convenience
graph = build_graph()
