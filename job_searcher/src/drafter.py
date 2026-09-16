"""Generates a targeted cold outreach email pitch."""
from __future__ import annotations

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from src.config import GEMINI_MODEL, require_gemini_key
from src.matcher import MatchResult
from src.parser import ParsedJob

PLACEHOLDER_EMAIL = "recruiter-email-not-found@example.com"


class EmailDraft(BaseModel):
    subject_line: str = Field(description="Punchy subject line")
    body: str = Field(description="Well-formatted email body, under 180 words")
    recipient_email: str = Field(description="Recruiter email, or a placeholder if not found")


def draft_email(job: ParsedJob, match: MatchResult, profile_markdown: str) -> EmailDraft:
    """Generate a concise, personalized cold email pitch for the given job."""
    client = genai.Client(api_key=require_gemini_key())

    recipient = job.recruiter_email or PLACEHOLDER_EMAIL

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=(
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
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=EmailDraft,
        ),
    )

    if response.parsed is None:
        raise RuntimeError("Gemini did not return a structured email draft")
    return response.parsed
