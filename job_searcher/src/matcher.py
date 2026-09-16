"""LLM evaluation & scoring of a parsed job against the user's profile."""
from __future__ import annotations

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from src.config import GEMINI_MODEL, MATCH_SCORE_THRESHOLD, require_gemini_key
from src.parser import ParsedJob


class MatchResult(BaseModel):
    match_score: int = Field(description="Overall match score, 0-100", ge=0, le=100)
    is_aligned: bool = Field(
        description=f"True if match_score >= {MATCH_SCORE_THRESHOLD} and the role's domain matches the profile"
    )
    matching_strengths: list[str] = Field(default_factory=list)
    missing_or_gap_skills: list[str] = Field(default_factory=list)
    verdict_summary: str = Field(description="A short explanation of the verdict")


def evaluate_match(job: ParsedJob, profile_markdown: str) -> MatchResult:
    """Score how well the candidate profile matches the parsed job."""
    client = genai.Client(api_key=require_gemini_key())

    job_summary = (
        f"Job Title: {job.job_title}\n"
        f"Company: {job.company_name}\n"
        f"Tech Stack: {', '.join(job.tech_stack) or 'N/A'}\n"
        f"Responsibilities:\n- " + "\n- ".join(job.responsibilities or ["N/A"])
    )

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=(
            "You are evaluating how well a candidate's profile matches a job description.\n"
            f"A match_score >= {MATCH_SCORE_THRESHOLD} combined with a matching domain "
            "(e.g. don't call a non-technical role aligned with a software engineer profile, "
            "and don't call a role aligned if the core tech stack is fundamentally different) "
            "should set is_aligned to true; otherwise set it to false.\n\n"
            f"CANDIDATE PROFILE:\n{profile_markdown}\n\n"
            f"JOB DESCRIPTION (parsed):\n{job_summary}"
        ),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=MatchResult,
        ),
    )

    if response.parsed is None:
        raise RuntimeError("Gemini did not return a structured match result")
    return response.parsed
