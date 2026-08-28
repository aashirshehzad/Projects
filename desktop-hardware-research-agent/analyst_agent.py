"""
Analyst Agent Module (Agent 2).

Critiques raw hardware research data for missing details, bottlenecks, and marketing bias,
producing a concise, internal technical evaluation for downstream synthesis.
"""

from dotenv import load_dotenv
from langchain_core.messages import BaseMessage, trim_messages
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_google_genai import ChatGoogleGenerativeAI

from state import AgentState

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


def run_analyst(state: AgentState) -> dict:
    """
    Critiques raw findings into a dense, internal technical evaluation of bottlenecks,
    synergy, and budget constraints without consumer-facing formatting.

    Args:
        state (AgentState): The current LangGraph state containing 'messages', 'query', 'budget', 'use_case', 'resolution', and 'research_data'.

    Returns:
        dict: State update dictionary with 'final_report'.
    """
    query = state.get("query", "").strip()
    budget = state.get("budget", "Flexible / Not specified").strip()
    use_case = state.get("use_case", "General").strip()
    resolution = state.get("resolution", "N/A").strip()
    research_data = state.get("research_data", "").strip()
    raw_messages = state.get("messages", [])

    trimmed_history = _trim_history(raw_messages, max_messages=8)

    if not query and trimmed_history:
        for msg in reversed(trimmed_history):
            if hasattr(msg, "content") and msg.content:
                query = str(msg.content).strip()
                break

    data_payload = research_data if research_data else "No external search data. Analyze based on standard hardware specs."

    # 1. Initialize LLM via Google Gemini
    llm = ChatGoogleGenerativeAI(
        model="gemini-3.5-flash-lite",
        temperature=0,
    )

    # 2. Define the Pure Technical Internal Analyst Prompt
    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            "You are an internal Senior Hardware Systems Analyst and Architecture Specialist.\n"
            "Your role is to perform raw technical evaluations and synergy audits on research findings. "
            "You provide internal analytical data for downstream processing, NOT end-user presentation.\n\n"
            "TARGET CONSTRAINTS:\n"
            "- Budget: {budget}\n"
            "- Primary Workload: {use_case}\n"
            "- Target Resolution: {resolution}\n\n"
            "OUTPUT DIRECTIVES:\n"
            "1. Output ONLY a concise, dense, unformatted technical evaluation focusing strictly on:\n"
            "   - Component Synergy & Architecture (CPU/GPU balance for {resolution} & {use_case})\n"
            "   - Bottleneck Risks (PCIe lanes, memory speed/latency sweet spots, VRAM adequacy)\n"
            "   - Power & Thermal Limits (PSU wattage headroom, VRM capability, cooler clearance)\n"
            "   - Budget & Cost Efficiency (Component pricing vs {budget})\n"
            "2. Keep the evaluation dense, analytical, and direct. DO NOT write greetings, conclusions, or full consumer report layouts.\n"
            "3. Address conversational context and iterative user adjustments (e.g. part swaps, cost reductions)."
        ),
        MessagesPlaceholder(variable_name="chat_history", optional=True),
        (
            "human",
            "Hardware Inquiry / Request:\n{query}\n\n"
            "Target Constraints:\n"
            "- Primary Use Case: {use_case}\n"
            "- Target Resolution: {resolution}\n"
            "- Allocated Budget: {budget}\n\n"
            "Raw Research Data gathered from the web:\n{research_data}\n\n"
            "Please provide the internal technical synergy and bottleneck evaluation."
        ),
    ])

    # 3. Assemble LCEL Chain: prompt | llm | StrOutputParser()
    chain = prompt | llm | StrOutputParser()

    # 4. Generate Final Technical Analysis
    report = chain.invoke({
        "query": query,
        "budget": budget,
        "use_case": use_case,
        "resolution": resolution,
        "research_data": data_payload,
        "chat_history": trimmed_history,
    })

    return {"final_report": report}
