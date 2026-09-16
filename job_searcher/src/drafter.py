"""Generates a short, templated cold outreach email pitch."""
from __future__ import annotations

import re

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from src.config import GEMINI_MODEL, require_gemini_key
from src.matcher import MatchResult
from src.parser import ParsedJob

PLACEHOLDER_EMAIL = "recruiter-email-not-found@example.com"

_NAME_HEADER_RE = re.compile(r"^##\s*Name\s*\n+(.+)$", re.MULTILINE)


class EmailDraft(BaseModel):
    subject_line: str = Field(description="Punchy subject line")
    body: str = Field(description="Well-formatted email body, under 180 words")
    recipient_email: str = Field(description="Recruiter email, or a placeholder if not found")


class _CandidateName(BaseModel):
    name: str = Field(description="The candidate's full name as it appears in the profile")


def _extract_candidate_name(profile_markdown: str) -> str:
    match = _NAME_HEADER_RE.search(profile_markdown)
    if match:
        return match.group(1).strip()

    client = genai.Client(api_key=require_gemini_key())
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=f"Extract the candidate's full name from this profile/resume:\n\n{profile_markdown}",
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=_CandidateName,
        ),
    )
    if response.parsed is None:
        return "the candidate"
    return response.parsed.name


def draft_email(job: ParsedJob, match: MatchResult, profile_markdown: str) -> EmailDraft:
    """Build a short, templated cold email pitch for the given job."""
    candidate_name = _extract_candidate_name(profile_markdown)
    greeting = job.recruiter_name.split()[0] if job.recruiter_name else "there"

    subject_line = f"Applying for {job.job_title}"
    body = (
        f"Hi {greeting},\n\n"
        f"I am applying for the {job.job_title} role at {job.company_name}. "
        "Please find my attached resume.\n\n"
        f"Best regards,\n{candidate_name}"
    )
    recipient_email = job.recruiter_email or PLACEHOLDER_EMAIL

    return EmailDraft(subject_line=subject_line, body=body, recipient_email=recipient_email)
