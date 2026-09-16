"""Extracts role, company, requirements, and recruiter info from a raw job description."""
from __future__ import annotations

import json

from anthropic import Anthropic
from pydantic import BaseModel, Field

from src.config import ANTHROPIC_MODEL, require_anthropic_key


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


_TOOL_NAME = "record_parsed_job"

_TOOL_SCHEMA = {
    "name": _TOOL_NAME,
    "description": "Record the structured fields extracted from a job description.",
    "input_schema": {
        "type": "object",
        "properties": {
            "job_title": {"type": "string"},
            "company_name": {"type": "string"},
            "recruiter_name": {"type": ["string", "null"]},
            "recruiter_email": {"type": ["string", "null"]},
            "tech_stack": {"type": "array", "items": {"type": "string"}},
            "responsibilities": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "job_title",
            "company_name",
            "recruiter_name",
            "recruiter_email",
            "tech_stack",
            "responsibilities",
        ],
    },
}


def parse_job_description(raw_text: str) -> ParsedJob:
    """Extract structured fields from a raw LinkedIn job description."""
    client = Anthropic(api_key=require_anthropic_key())

    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=1500,
        tools=[_TOOL_SCHEMA],
        tool_choice={"type": "tool", "name": _TOOL_NAME},
        messages=[
            {
                "role": "user",
                "content": (
                    "Extract structured fields from the following job description. "
                    "If a recruiter/hiring manager name or email is not present, use null. "
                    "List tech stack as short items (e.g. 'Python', 'AWS'). "
                    "List responsibilities/requirements as concise bullet-style strings.\n\n"
                    f"JOB DESCRIPTION:\n{raw_text}"
                ),
            }
        ],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == _TOOL_NAME:
            return ParsedJob.model_validate(block.input)

    raise RuntimeError("Claude did not return structured job data")
