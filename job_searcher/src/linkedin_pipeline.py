"""Drains pending LinkedIn DMs (data/linkedin_messages.db) into Gmail drafts.

For each unprocessed row left by linkedin_dm_fetcher/, resolves job-posting
text (the message body, or by following an attached LinkedIn post URL), then
runs it through the same parse -> match -> draft -> Gmail-draft pipeline as
main.py, and marks the row processed on success.
"""
from __future__ import annotations

import sqlite3
import sys

from rich.console import Console
from rich.panel import Panel

from backend.job_fetcher import fetch_job_text, looks_like_url
from src import storage
from src.config import BASE_DIR, PROFILE_PATH
from src.drafter import draft_email
from src.gmail_client import create_draft
from src.matcher import evaluate_match
from src.parser import parse_job_description

console = Console()

DB_PATH = BASE_DIR / "data" / "linkedin_messages.db"


def _resolve_job_text(row: sqlite3.Row) -> str | None:
    text = (row["text"] or "").strip()
    if text:
        return text

    attachment_url = row["attachment_url"]
    if attachment_url and looks_like_url(attachment_url):
        try:
            return fetch_job_text(attachment_url)
        except ValueError as e:
            console.print(f"[yellow]Could not read attachment URL: {e}[/yellow]")
            return None

    return None


def _mark_processed(conn: sqlite3.Connection, message_id: str) -> None:
    conn.execute("UPDATE linkedin_messages SET processed = 1 WHERE id = ?", (message_id,))
    conn.commit()


def main() -> None:
    if not DB_PATH.exists():
        console.print(f"[red]No LinkedIn messages DB found at {DB_PATH}. Run the fetcher first.[/red]")
        sys.exit(1)

    if not PROFILE_PATH.exists():
        console.print(f"[red]Profile not found at {PROFILE_PATH}[/red]")
        sys.exit(1)
    profile_markdown = PROFILE_PATH.read_text(encoding="utf-8")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    pending = conn.execute(
        "SELECT * FROM linkedin_messages WHERE processed = 0 ORDER BY timestamp ASC"
    ).fetchall()

    if not pending:
        console.print("[green]No pending LinkedIn DMs to process.[/green]")
        conn.close()
        return

    console.print(f"[bold]{len(pending)} pending LinkedIn DM(s) found.[/bold]\n")

    for row in pending:
        console.rule(f"Message {row['id']} from {row['sender_name'] or row['sender_urn']}")

        job_text = _resolve_job_text(row)
        if not job_text:
            console.print(
                "[yellow]No usable job text (empty message and no readable attachment link). "
                "Leaving unprocessed.[/yellow]\n"
            )
            continue

        try:
            with console.status("[bold]Parsing job description..."):
                job = parse_job_description(job_text)
        except Exception as e:
            console.print(f"[red]Failed to parse job description: {e}[/red]\n")
            continue

        console.print(
            Panel(
                f"[bold]{job.job_title}[/bold] @ [bold]{job.company_name}[/bold]\n"
                f"Recruiter: {job.recruiter_name or 'N/A'} <{job.recruiter_email or 'N/A'}>",
                title="Parsed Job",
            )
        )

        with console.status("[bold]Evaluating match against your profile..."):
            match = evaluate_match(job, profile_markdown)
        console.print(
            f"Match score: {match.match_score}% "
            f"({'aligned' if match.is_aligned else 'not aligned'})"
        )

        with console.status("[bold]Drafting cold outreach email..."):
            email = draft_email(job, match, profile_markdown)

        console.print(
            Panel(
                f"[bold]To:[/bold] {email.recipient_email}\n"
                f"[bold]Subject:[/bold] {email.subject_line}\n\n{email.body}",
                title="Generated Email Draft",
            )
        )

        try:
            with console.status("[bold]Saving draft to Gmail..."):
                draft_id = create_draft(email)
        except RuntimeError as e:
            console.print(f"[red]Failed to save Gmail draft: {e}[/red]\n")
            storage.append_entry(
                company=job.company_name,
                title=job.job_title,
                match_score=match.match_score,
                is_aligned=match.is_aligned,
                draft_status="draft_failed",
            )
            continue

        storage.append_entry(
            company=job.company_name,
            title=job.job_title,
            match_score=match.match_score,
            is_aligned=match.is_aligned,
            draft_status="draft_created",
            draft_id=draft_id,
        )
        _mark_processed(conn, row["id"])
        console.print(f"[green]Draft saved to Gmail (id: {draft_id}) and message marked processed.[/green]\n")

    conn.close()


if __name__ == "__main__":
    main()
