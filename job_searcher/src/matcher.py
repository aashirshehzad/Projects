"""LLM evaluation & scoring of a parsed job against the user's profile."""
from __future__ import annotations

from anthropic import Anthropic
from pydantic import BaseModel, Field

from src.config import ANTHROPIC_MODEL, MATCH_SCORE_THRESHOLD, require_anthropic_key
from src.parser import ParsedJob


class MatchResult(BaseModel):
    match_score: int = Field(description="Overall match score, 0-100", ge=0, le=100)
    is_aligned: bool = Field(
        description=f"True if match_score >= {MATCH_SCORE_THRESHOLD} and the role's domain matches the profile"
    )
    matching_strengths: list[str] = Field(default_factory=list)
    missing_or_gap_skills: list[str] = Field(default_factory=list)
    verdict_summary: str = Field(description="A short explanation of the verdict")


_TOOL_NAME = "record_match_result"

_TOOL_SCHEMA = {
    "name": _TOOL_NAME,
    "description": "Record the match evaluation between a candidate profile and a job description.",
    "input_schema": {
        "type": "object",
        "properties": {
            "match_score": {"type": "integer", "minimum": 0, "maximum": 100},
            "is_aligned": {"type": "boolean"},
            "matching_strengths": {"type": "array", "items": {"type": "string"}},
            "missing_or_gap_skills": {"type": "array", "items": {"type": "string"}},
            "verdict_summary": {"type": "string"},
        },
        "required": [
            "match_score",
            "is_aligned",
            "matching_strengths",
            "missing_or_gap_skills",
            "verdict_summary",
        ],
    },
}


def evaluate_match(job: ParsedJob, profile_markdown: str) -> MatchResult:
    """Score how well the candidate profile matches the parsed job."""
    client = Anthropic(api_key=require_anthropic_key())

    job_summary = (
        f"Job Title: {job.job_title}\n"
        f"Company: {job.company_name}\n"
        f"Tech Stack: {', '.join(job.tech_stack) or 'N/A'}\n"
        f"Responsibilities:\n- " + "\n- ".join(job.responsibilities or ["N/A"])
    )

    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=1500,
        tools=[_TOOL_SCHEMA],
        tool_choice={"type": "tool", "name": _TOOL_NAME},
        messages=[
            {
                "role": "user",
                "content": (
                    "You are evaluating how well a candidate's profile matches a job description.\n"
                    f"A match_score >= {MATCH_SCORE_THRESHOLD} combined with a matching domain "
                    "(e.g. don't call a non-technical role aligned with a software engineer profile, "
                    "and don't call a role aligned if the core tech stack is fundamentally different) "
                    "should set is_aligned to true; otherwise set it to false.\n\n"
                    f"CANDIDATE PROFILE:\n{profile_markdown}\n\n"
                    f"JOB DESCRIPTION (parsed):\n{job_summary}"
                ),
            }
        ],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == _TOOL_NAME:
            return MatchResult.model_validate(block.input)

    raise RuntimeError("Claude did not return a structured match result")
