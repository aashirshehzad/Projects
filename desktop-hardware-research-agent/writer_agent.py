"""
Writer Agent Module (Agent 3).

Synthesizes technical analysis and research data into a context-aware presentation tailored for the user.
Acts as a helpful, conversational AI hardware assistant, dynamically routing between full, structured
editorial reports for brand new PC builds and concise, direct conversational responses for follow-up questions.
"""

import sys
import asyncio
from dotenv import load_dotenv
from langchain_core.messages import BaseMessage, AIMessage, trim_messages
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


def run_writer(state: AgentState) -> dict:
    """
    Acts as a helpful, conversational AI hardware assistant. Analyzes user context and dynamically
    selects between a comprehensive structured Markdown report for new PC builds, or a concise,
    conversational 1-3 paragraph answer for follow-up inquiries and component modifications.

    Args:
        state (AgentState): The current LangGraph state containing 'messages', 'query', 'budget',
                            'use_case', 'resolution', 'research_data', and 'final_report'.

    Returns:
        dict: State update dictionary with 'final_article' and new AIMessage appended to 'messages'.
    """
    query = state.get("query", "").strip()
    budget = state.get("budget", "Flexible / Not specified").strip()
    use_case = state.get("use_case", "General").strip()
    resolution = state.get("resolution", "N/A").strip()
    research_data = state.get("research_data", "").strip()
    final_report = state.get("final_report", "").strip()
    raw_messages = state.get("messages", [])

    trimmed_history = _trim_history(raw_messages, max_messages=8)

    # Derive query from latest human message if query string is empty
    if not query and trimmed_history:
        for msg in reversed(trimmed_history):
            if hasattr(msg, "content") and msg.content:
                query = str(msg.content).strip()
                break

    # Consolidate available technical context (Analyst synthesis and/or raw Researcher findings)
    context_sections = []
    if final_report:
        context_sections.append(f"Analyst Technical Synthesis:\n{final_report}")
    if research_data:
        context_sections.append(f"Researcher Live Web Findings:\n{research_data}")

    combined_hardware_data = (
        "\n\n".join(context_sections)
        if context_sections
        else "No external search data retrieved. Rely on expert hardware knowledge and conversation context."
    )

    # 1. Initialize LLM via Google Gemini
    llm = ChatGoogleGenerativeAI(
        model="gemini-3.5-flash-lite",
        temperature=0.3,
    )

    # 2. Context-Aware, Conversational System Prompt with Strict Formatting Rules
    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            "You are a helpful, context-aware, and highly skilled Conversational AI Hardware Assistant.\n\n"
            "Your role is to analyze the conversation history and the user's latest message to deliver "
            "an appropriately formatted response using the provided hardware research and analyst findings.\n\n"
            "USER CONSTRAINTS & CONTEXT:\n"
            "- Target Budget: {budget}\n"
            "- Intended Use Case: {use_case}\n"
            "- Target Display Resolution: {resolution}\n\n"
            "STRICT FORMATTING & ROUTING RULES:\n"
            "Carefully analyze the user's latest query in the context of the chat history to determine their intent:\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "CASE 1: COMPLETELY NEW PC BUILD REQUEST\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "TRIGGER: The user is asking for a brand new PC build recommendation, a full parts list, or a complete system configuration from scratch.\n"
            "ACTION: Output a publication-grade, beautifully structured Markdown report containing the following sections:\n"
            "  # [Engaging & Specific PC Build Title]\n"
            "  ## ⚡ Executive Summary & Key Takeaways\n"
            "  - Bulleted summary highlighting build philosophy, performance targets ({use_case} @ {resolution}), and total budget utilization ({budget}).\n"
            "  ## 🔬 Architectural & Synergy Breakdown\n"
            "  - Deep dive into CPU & GPU pairing, thermal considerations, RAM speed/latency, and storage speed.\n"
            "  ## 📊 Complete Component & Pricing Table\n"
            "  - Markdown table with columns: | Component | Model | Key Specs | Est. Price ($) | Notes |\n"
            "  ## 💰 Budget & Value Analysis\n"
            "  - Cost efficiency evaluation against the {budget} ceiling and performance-per-dollar rationale.\n"
            "  ## 💡 Final Buyer's Verdict & Upgrade Headroom\n"
            "  - Actionable guidance, upgrade path recommendations, and final tips for the builder.\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "CASE 2: FOLLOW-UP QUESTION, PART MODIFICATION, OR QUICK INQUIRY\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "TRIGGER: The user is asking a follow-up question, seeking clarification, asking about alternative options, "
            "requesting part swaps, or refining an existing recommendation (e.g., 'What RAM options do I have?', 'Can I swap to Intel?', 'Is a 750W PSU enough?', 'Can you make it $150 cheaper?', 'ddr 4 32gb ram and ryzen 3600 are good enough').\n"
            "ACTION: STRICTLY IGNORE THE MULTI-PAGE REPORT TEMPLATE!\n"
            "  1. Answer directly, conversationally, and concisely in 1 to 3 short paragraphs based on the provided technical findings.\n"
            "  2. DO NOT include massive specs tables, full component lists, repetitive executive summaries, or heavy boilerplate formatting.\n"
            "  3. If listing 2-3 specific component alternatives (e.g. comparing two RAM kits), use a concise bulleted list instead of a full-page table.\n"
            "  4. Maintain an encouraging, knowledgeable, and helpful tone focused squarely on answering the exact question asked."
        ),
        MessagesPlaceholder(variable_name="chat_history", optional=True),
        (
            "human",
            "User Hardware Query / Request:\n{query}\n\n"
            "Target Constraints:\n"
            "- Primary Use Case: {use_case}\n"
            "- Target Resolution: {resolution}\n"
            "- Target Budget Ceiling: {budget}\n\n"
            "Hardware Technical Findings & Research Context:\n{final_report}\n\n"
            "Please analyze the latest user message and conversation context, then provide the appropriate response adhering strictly to the formatting rules."
        ),
    ])

    # 3. Assemble LCEL Chain: prompt | llm | StrOutputParser()
    chain = prompt | llm | StrOutputParser()

    # 4. Generate Final Response
    response_text = chain.invoke({
        "query": query,
        "budget": budget,
        "use_case": use_case,
        "resolution": resolution,
        "final_report": combined_hardware_data,
        "chat_history": trimmed_history,
    })

    return {
        "final_article": response_text,
        "messages": [AIMessage(content=response_text)],
    }
