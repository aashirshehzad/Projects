"""
LangGraph Workflow Orchestrator Module with Neon AsyncPostgresSaver Checkpointer & Conditional Routing.

Coordinates dynamic execution across specialized agent nodes with persistent asynchronous state:
- START -> Researcher (Web Search)
- Researcher -> [Conditional Edge: route_after_research]
    -> "Analyst" (Deep Technical Synthesis & Bottleneck Critique) -> Writer -> END
    -> "Writer" (Direct Context-Aware & Conversational Presentation) -> END
"""

import sys
import os
import uuid
import asyncio
from typing import Optional, Any
from dotenv import load_dotenv

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import psycopg
from psycopg import AsyncConnection
from psycopg.rows import dict_row, DictRow
from psycopg_pool import AsyncConnectionPool

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, trim_messages
from langchain_core.runnables import RunnableConfig
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph

from state import AgentState
from research_agent import run_researcher
from analyst_agent import run_analyst
from writer_agent import run_writer

load_dotenv()

# Load Neon Postgres Database URL from environment
NEON_URI = os.environ.get("NEON_DATABASE_URL")


def _validate_environment() -> None:
    """Validates necessary API keys and database configuration before running the workflow."""
    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    tavily_key = os.getenv("TAVILY_API_KEY")
    neon_uri = os.environ.get("NEON_DATABASE_URL")
    missing = []
    if not gemini_key:
        missing.append("GEMINI_API_KEY (or GOOGLE_API_KEY)")
    if not tavily_key:
        missing.append("TAVILY_API_KEY")
    if not neon_uri:
        missing.append("NEON_DATABASE_URL")
    if missing:
        raise ValueError(
            f"Missing required environment variable(s): {', '.join(missing)}. "
            "Please ensure GEMINI_API_KEY, TAVILY_API_KEY, and NEON_DATABASE_URL are configured."
        )


def trim_conversation_history(messages: list[BaseMessage], max_messages: int = 8) -> list[BaseMessage]:
    """
    Trims conversation history to the most recent 6-8 messages to prevent context bloat and token exhaustion
    while preserving dialogue continuity and starting on a user turn.
    """
    if not messages:
        return []
    try:
        return trim_messages(
            messages,
            max_tokens=max_messages,
            strategy="last",
            token_counter=len,
            start_on="human",
            allow_partial=False,
        )
    except Exception:
        return messages[-max_messages:]


async def route_after_research(state: AgentState) -> str:
    """
    Dynamically routes execution following the Researcher node:
    - Returns 'Analyst' for complete PC builds, major architectural overhauls, or explicit bottleneck/synergy queries.
    - Returns 'Writer' for quick follow-ups, minor part swaps, or direct component clarifications.
    """
    query = state.get("query", "").strip()
    messages = state.get("messages", [])

    if not query and messages:
        for msg in reversed(messages):
            if hasattr(msg, "content") and msg.content:
                query = str(msg.content).strip()
                break

    if not query:
        return "Analyst"

    q_lower = query.lower()

    # 1. Fast deterministic heuristic: Deep bottleneck, synergy, or comprehensive audit checks
    deep_keywords = [
        "bottleneck", "synergy", "deep dive", "full analysis", "architectural",
        "benchmarks", "vrm", "pcie lane", "comprehensive"
    ]
    if any(kw in q_lower for kw in deep_keywords):
        return "Analyst"

    # 2. Fast deterministic heuristic: New PC build inquiries
    build_keywords = [
        "pc build", "new build", "full build", "build me", "gaming rig",
        "workstation build", "complete setup", "entire system", "parts list"
    ]
    if any(kw in q_lower for kw in build_keywords):
        return "Analyst"

    # 3. Initial turn asking for a complete computer recommendation
    if len(messages) <= 1 and any(w in q_lower for w in ["build", "pc", "rig", "computer", "system", "setup", "recommend a"]):
        return "Analyst"

    # 4. Fast deterministic heuristic: Quick follow-ups / single part inquiries route directly to Writer
    quick_patterns = [
        "what ram", "what gpu", "what cpu", "switch to", "change to", "swap",
        "cheaper", "how much", "can i", "is it compatible", "psu enough",
        "difference between", "better option", "upgrade ram", "case option"
    ]
    if any(kw in q_lower for kw in quick_patterns):
        return "Writer"

    # 5. Lightweight LLM classifier for ambiguous queries
    try:
        classifier_llm = ChatGoogleGenerativeAI(
            model="gemini-3.5-flash-lite",
            temperature=0,
        )
        classification_prompt = [
            SystemMessage(content=(
                "You are an intent router for a PC Hardware Multi-Agent System.\n"
                "Classify whether the user query requires a full in-depth bottleneck & architectural engineering analysis (ANALYST) "
                "or if it is a quick follow-up, minor component swap, clarification, or conversational question (WRITER).\n\n"
                "Rules:\n"
                "- Output 'ANALYST' if the user asks for a complete PC build, major overhaul, or deep bottleneck/synergy critique.\n"
                "- Output 'WRITER' if the user asks a quick follow-up, single-part question, simple tweak, or clarification.\n"
                "Respond ONLY with 'ANALYST' or 'WRITER'."
            )),
            HumanMessage(content=f"User Query: {query}")
        ]
        res = await classifier_llm.ainvoke(classification_prompt)
        decision = str(res.content).strip().upper()
        if "WRITER" in decision:
            return "Writer"
        return "Analyst"
    except Exception:
        # Fallback: if in active conversation and query is short, prefer fast direct Writer response
        if len(messages) > 1 and len(query) < 80:
            return "Writer"
        return "Analyst"


def create_graph_builder() -> StateGraph:
    """
    Constructs and returns the StateGraph builder with registered agent nodes and conditional routing:
    START -> Researcher -> (Conditional: Analyst or Writer) -> Writer -> END.
    """
    builder = StateGraph(AgentState) # type: ignore[type-var]

    # Register Agent Nodes
    builder.add_node("Researcher", run_researcher)
    builder.add_node("Analyst", run_analyst)
    builder.add_node("Writer", run_writer)

    # 1. Start pipeline at Researcher
    builder.add_edge(START, "Researcher")

    # 2. Dynamic Routing after Researcher: skip Analyst for simple/follow-up queries
    builder.add_conditional_edges(
        "Researcher",
        route_after_research,
        {
            "Analyst": "Analyst",
            "Writer": "Writer",
            "analyst": "Analyst",
            "writer": "Writer",
        },
    )

    # 3. If routed to Analyst, proceed to Writer for final presentation
    builder.add_edge("Analyst", "Writer")

    # 4. Writer terminates the graph
    builder.add_edge("Writer", END)

    return builder


# Global state for managing the async pool and compiled graph singleton
_async_pool: Optional[AsyncConnectionPool[AsyncConnection[DictRow]]] = None
_async_checkpointer: Optional[AsyncPostgresSaver] = None
_async_graph: Optional[CompiledStateGraph] = None
_init_lock = asyncio.Lock()


async def get_async_graph() -> CompiledStateGraph:
    """
    Asynchronously initializes and compiles the LangGraph workflow with AsyncPostgresSaver checkpointer.
    Thread-safe and cached for reuse across FastAPI requests.
    """
    global _async_pool, _async_checkpointer, _async_graph

    if _async_graph is not None:
        return _async_graph

    async with _init_lock:
        if _async_graph is not None:
            return _async_graph

        builder = create_graph_builder()

        if NEON_URI:
            connection_kwargs = {
                "autocommit": True,
                "prepare_threshold": 0,
                "row_factory": dict_row,
            }
            # AsyncConnectionPool with health check prevents "SSL connection has been closed unexpectedly" on idle serverless Neon
            _async_pool = AsyncConnectionPool[AsyncConnection[DictRow]](
                conninfo=NEON_URI,
                max_size=20,
                kwargs=connection_kwargs,
                check=AsyncConnectionPool.check_connection,
                max_idle=300,
                open=False,
            )
            await _async_pool.open()
            _async_checkpointer = AsyncPostgresSaver(_async_pool)
            await _async_checkpointer.setup()  # Ensures checkpoint tables exist in Neon Postgres
            _async_graph = builder.compile(checkpointer=_async_checkpointer)
        else:
            memory = MemorySaver()
            _async_graph = builder.compile(checkpointer=memory)

        return _async_graph


async def close_async_graph() -> None:
    """Closes the underlying async connection pool during application shutdown."""
    global _async_pool, _async_checkpointer, _async_graph
    if _async_pool is not None:
        await _async_pool.close()
        _async_pool = None
    _async_checkpointer = None
    _async_graph = None


async def aexecute_graph(
    query: str,
    budget: str = "$1,500 Max",
    use_case: str = "Gaming",
    resolution: str = "1440p",
    thread_id: Optional[str] = None,
) -> dict:
    """
    Asynchronously executes the multi-agent research pipeline for a given desktop hardware query with custom constraints
    and persistent short-term thread session memory stored in Neon Postgres.
    """
    if not query or not query.strip():
        raise ValueError("Query cannot be empty. Please enter a valid desktop PC model or component query.")

    _validate_environment()

    # Assign or preserve session thread ID
    active_thread_id = thread_id if thread_id else str(uuid.uuid4())
    config: RunnableConfig = {"configurable": {"thread_id": active_thread_id}}

    initial_state: AgentState = {
        "messages": [HumanMessage(content=query.strip())],
        "query": query.strip(),
        "budget": budget.strip() if budget else "$1,500 Max",
        "use_case": use_case.strip() if use_case else "Gaming",
        "resolution": resolution.strip() if resolution else "1440p",
        "research_data": "",
        "final_report": "",
        "final_article": "",
    }

    graph = await get_async_graph()
    final_state = await graph.ainvoke(initial_state, config=config)
    return final_state


def execute_graph(
    query: str,
    budget: str = "$1,500 Max",
    use_case: str = "Gaming",
    resolution: str = "1440p",
    thread_id: Optional[str] = None,
) -> dict:
    """Synchronous wrapper around aexecute_graph for CLI or testing scripts."""
    return asyncio.run(
        aexecute_graph(
            query=query,
            budget=budget,
            use_case=use_case,
            resolution=resolution,
            thread_id=thread_id,
        )
    )
