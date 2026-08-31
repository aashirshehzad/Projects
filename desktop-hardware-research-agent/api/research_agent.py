"""
Research Agent Module (Agent 1).

Autonomously queries Tavily Search to gather raw hardware specifications, benchmark metrics,
wattage/TDP, and market pricing for desktop computer components using Google Gemini,
constrained by budget, intended use case, target resolution, and conversational dialogue context.
"""

import os
import sys
from typing import Any
from dotenv import load_dotenv

from langchain_core.messages import BaseMessage, trim_messages
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_google_genai import ChatGoogleGenerativeAI
try:
    from langchain_tavily import TavilySearchResults  # type: ignore
except ImportError:
    try:
        from langchain_tavily import TavilySearch as TavilySearchResults  # type: ignore
    except ImportError:
        from langchain_community.tools.tavily_search import TavilySearchResults  # type: ignore

try:
    from langchain.agents import create_tool_calling_agent, AgentExecutor  # type: ignore
except (ImportError, AttributeError, Exception):
    create_tool_calling_agent = None  # type: ignore
    AgentExecutor = None  # type: ignore

try:
    from state import AgentState
except ImportError:
    from api.state import AgentState

load_dotenv()


def _trim_history(messages: list[BaseMessage], max_messages: int = 8) -> list[BaseMessage]:
    """Trims message history to the most recent 6-8 messages starting on a human turn."""
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


def _format_agent_output(raw_output: Any) -> str:
    """Helper to convert structured agent output to a clean string."""
    if isinstance(raw_output, str):
        return raw_output
    if isinstance(raw_output, list):
        parts = []
        for item in raw_output:
            if isinstance(item, dict) and "text" in item:
                parts.append(item["text"])
            elif isinstance(item, str):
                parts.append(item)
            else:
                parts.append(str(item))
        return "".join(parts)
    return str(raw_output)


def _format_search_results(results: Any) -> str:
    """Formats raw Tavily search results into clean bullet points."""
    if isinstance(results, list):
        formatted = []
        for idx, item in enumerate(results, 1):
            if isinstance(item, dict):
                title = item.get("title", f"Result {idx}")
                content = item.get("content", "")
                url = item.get("url", "")
                formatted.append(f"- **{title}**: {content} (Source: {url})")
            else:
                formatted.append(f"- {str(item)}")
        return "\n".join(formatted)
    return str(results)


def run_researcher(state: AgentState) -> dict:
    """
    Executes web research using Tavily Search and Google Gemini to gather raw hardware specs and pricing
    under strict budget, use-case, resolution, and conversational context constraints.

    Args:
        state (AgentState): The current LangGraph state containing 'messages', 'query', 'budget', 'use_case', 'resolution'.

    Returns:
        dict: State update dictionary with 'research_data'.
    """
    query = state.get("query", "").strip()
    budget = state.get("budget", "Flexible / Not specified").strip()
    use_case = state.get("use_case", "General").strip()
    resolution = state.get("resolution", "N/A").strip()
    raw_messages = state.get("messages", [])

    # Trim conversational context to the last 6-8 messages
    trimmed_history = _trim_history(raw_messages, max_messages=8)

    # Derive query from latest human message if query string is empty
    if not query and trimmed_history:
        for msg in reversed(trimmed_history):
            if hasattr(msg, "content") and msg.content:
                query = str(msg.content).strip()
                break

    if not query:
        return {"research_data": "No query provided for research."}

    # 1. Initialize Tavily Web Search Tool with max_results=3
    search_tool = TavilySearchResults(
        max_results=3,
        description=(
            "Search the web for up-to-date desktop PC hardware specifications, benchmark results, "
            "detailed component breakdowns (CPU, GPU, RAM, Storage, Motherboard, PSU), "
            "wattage/TDP requirements, and live retail pricing matching specific budget and workload criteria."
        )
    )
    tools = [search_tool]

    # 2. Initialize LLM via Google Gemini
    llm = ChatGoogleGenerativeAI(
        model="gemini-3.5-flash-lite",
        temperature=0,
    )

    # 3. Define the Researcher Agent Prompt strictly for raw data extraction
    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            "You are an autonomous PC Hardware Research Data Engine. Your SOLE objective is to retrieve and output verified, raw factual data: component specs, clock speeds, TDP/power metrics, benchmark figures, and retail pricing from Tavily Search.\n\n"
            "TARGET CONSTRAINTS & REQUIREMENTS:\n"
            "- Target Budget Ceiling: {budget}\n"
            "- Primary Use Case: {use_case}\n"
            "- Target Display Resolution: {resolution}\n\n"
            "STRICT RESEARCH DIRECTIVES:\n"
            "1. Output ONLY concise raw data, specifications, and verified pricing organized into bullet points.\n"
            "2. DO NOT write greetings, intros, conclusions, summaries, commentary, or conversational prose.\n"
            "3. Focus search queries strictly around hardware matching the user's workload, resolution, budget, and conversation history.\n"
            "4. MAXIMUM of 1 search tool call. Once search results are returned, immediately output your factual bulleted data."
        ),
        MessagesPlaceholder(variable_name="chat_history", optional=True),
        (
            "human",
            "Hardware Query / Request: {input}\n"
            "Primary Use Case: {use_case}\n"
            "Target Resolution: {resolution}\n"
            "Budget Ceiling: {budget}\n\n"
            "Please extract and output only verified component specs, benchmark numbers, power ratings, and live prices in bullet points."
        ),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])

    # 4. Assemble Agent & Executor with circuit breaker and intermediate step retention (if available)
    if create_tool_calling_agent is not None and AgentExecutor is not None:
        try:
            agent = create_tool_calling_agent(llm=llm, tools=tools, prompt=prompt)
            agent_executor = AgentExecutor(
                agent=agent,
                tools=tools,
                verbose=False,
                handle_parsing_errors=True,
                max_iterations=2,
                return_intermediate_steps=True,
            )
            result = agent_executor.invoke({
                "input": query,
                "query": query,
                "budget": budget,
                "use_case": use_case,
                "resolution": resolution,
                "chat_history": trimmed_history,
            })
            raw_output = result.get("output", "")
            intermediate_steps = result.get("intermediate_steps", [])

            # If LLM completed successfully without hitting max iteration warning
            if raw_output and "Agent stopped due to max iterations" not in raw_output:
                formatted_data = _format_agent_output(raw_output)
                if len(formatted_data.strip()) > 30:
                    return {"research_data": formatted_data}

            # Fallback 1: Extract tool findings directly from intermediate steps
            if intermediate_steps:
                collected_obs = []
                for action, observation in intermediate_steps:
                    if observation:
                        collected_obs.append(_format_search_results(observation))
                if collected_obs:
                    return {"research_data": "\n".join(collected_obs)}

        except Exception:
            pass

    # Fallback 2: Direct targeted Tavily query to guarantee research data is never empty
    try:
        direct_search_query = f"{query} {use_case} {resolution} {budget} PC build parts specs price benchmarks".strip()
        direct_results = search_tool.invoke({"query": direct_search_query})
        return {"research_data": _format_search_results(direct_results)}
    except Exception as ex:
        return {"research_data": f"Failed to retrieve hardware research data: {str(ex)}"}
