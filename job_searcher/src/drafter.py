"""Generates a targeted cold outreach email pitch."""
from __future__ import annotations

from anthropic import Anthropic
from pydantic import BaseModel, Field

from src.config import ANTHROPIC_MODEL, require_anthropic_key
from src.matcher import MatchResult
from src.parser import ParsedJob

PLACEHOLDER_EMAIL = "recruiter-email-not-found@example.com"


class EmailDraft(BaseModel):
    subject_line: str = Field(description="Punchy subject line")
    body: str = Field(description="Well-formatted email body, under 180 words")
    recipient_email: str = Field(description="Recruiter email, or a placeholder if not found")


_TOOL_NAME = "record_email_draft"

_TOOL_SCHEMA = {
    "name": _TOOL_NAME,
    "description": "Record a generated cold outreach email pitch.",
    "input_schema": {
        "type": "object",
        "properties": {
            "subject_line": {"type": "string"},
            "body": {"type": "string"},
            "recipient_email": {"type": "string"},
        },
        "required": ["subject_line", "body", "recipient_email"],
    },
}


def draft_email(job: ParsedJob, match: MatchResult, profile_markdown: str) -> EmailDraft:
    """Generate a concise, personalized cold email pitch for the given job."""
    client = Anthropic(api_key=require_anthropic_key())

    recipient = job.recruiter_email or PLACEHOLDER_EMAIL

    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=1200,
        tools=[_TOOL_SCHEMA],
        tool_choice={"type": "tool", "name": _TOOL_NAME},
        messages=[
            {
                "role": "user",
                "content": (
                    "Write a cold outreach email from the candidate described in the profile below, "
                    f"applying for the '{job.job_title}' role at {job.company_name}"
                    + (f", addressed to {job.recruiter_name}" if job.recruiter_name else "")
                    + ".\n\n"
                    "Requirements:\n"
                    "- Sign the email with the candidate's actual name, as found in the profile.\n"
                    "- Under 180 words total in the body.\n"
                    "- Engaging, concise, confident tone; no generic filler.\n"
                    "- Pull 2-3 of the most relevant project or experience highlights from the "
                    "candidate profile below that directly address the job's tech stack/responsibilities.\n"
                    "- subject_line format like '[Role] Application - [Name] | [Key Tech] Specialist'.\n"
                    "- If a matching gap exists, do not dwell on it; focus on strengths.\n"
                    f"- recipient_email should be '{recipient}' verbatim.\n\n"
                    f"CANDIDATE PROFILE:\n{profile_markdown}\n\n"
                    f"JOB TITLE: {job.job_title}\n"
                    f"COMPANY: {job.company_name}\n"
                    f"TECH STACK: {', '.join(job.tech_stack) or 'N/A'}\n"
                    "RESPONSIBILITIES:\n- " + "\n- ".join(job.responsibilities or ["N/A"]) + "\n\n"
                    f"MATCHING STRENGTHS (per prior evaluation): {', '.join(match.matching_strengths) or 'N/A'}"
                ),
            }
        ],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == _TOOL_NAME:
            return EmailDraft.model_validate(block.input)

    raise RuntimeError("Claude did not return a structured email draft")
