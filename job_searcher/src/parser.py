"""Extracts role, company, requirements, and recruiter info from a raw job description."""
from __future__ import annotations

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from src.config import GEMINI_MODEL, require_gemini_key


class ParsedJob(BaseModel):
    job_title: str = Field(description="The job title, e.g. 'Senior Backend Engineer'")
    company_name: str = Field(description="The hiring company's name")
    recruiter_name: str | None = Field(
        default=None, description="Recruiter or hiring manager name, if mentioned"
    )
    recruiter_email: str | None = Field(
        default=None, description="Recruiter or hiring manager email, if mentioned"
    )
    tech_stack: list[str] = Field(
        default_factory=list, description="Key technologies/tools mentioned in the JD"
    )
    responsibilities: list[str] = Field(
        default_factory=list, description="Key responsibilities/requirements from the JD"
    )


def parse_job_description(raw_text: str) -> ParsedJob:
    """Extract structured fields from a raw LinkedIn job description."""
    client = genai.Client(api_key=require_gemini_key())

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=(
            "Extract structured fields from the following job description. "
            "If a recruiter/hiring manager name or email is not present, use null. "
            "List tech stack as short items (e.g. 'Python', 'AWS'). "
            "List responsibilities/requirements as concise bullet-style strings.\n\n"
            f"JOB DESCRIPTION:\n{raw_text}"
        ),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ParsedJob,
        ),
    )

    if response.parsed is None:
        raise RuntimeError("Gemini did not return structured job data")
    return response.parsed
