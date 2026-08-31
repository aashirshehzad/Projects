"""
State schema definition for the Desktop PC Hardware Research Multi-Agent System.
"""

from typing import Annotated
from typing_extensions import TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """
    Shared state schema passed between LangGraph sequential agent nodes with chat history support.

    Attributes:
        messages (Annotated[list[BaseMessage], add_messages]): Cumulative conversation history accumulating user & AI turns.
        query (str): The initial or latest hardware query provided by the user.
        budget (str): User-specified budget ceiling or target price range (e.g. "$1,200 - $1,500" or "$2,000 Max").
        use_case (str): Primary intended workload (e.g. "Gaming", "Video Editing / Rendering", "AI/ML & Deep Learning").
        resolution (str): Target display resolution (e.g. "1080p", "1440p", "4K", "N/A (Workstation)").
        research_data (str): The structured raw web search & spec findings gathered by the Researcher agent (Agent 1).
        final_report (str): The synthesized technical analysis and bottleneck critique produced by the Analyst agent (Agent 2).
        final_article (str): The publication-ready editorial article drafted by the Writer agent (Agent 3).
    """
    messages: Annotated[list[BaseMessage], add_messages]
    query: str
    budget: str
    use_case: str
    resolution: str
    research_data: str
    final_report: str
    final_article: str
