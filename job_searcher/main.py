"""JobAgent: interactive CLI entry point."""
from __future__ import annotations

import sys

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from src import storage
from src.config import MATCH_SCORE_THRESHOLD, PROFILE_PATH
from src.drafter import draft_email
from src.gmail_client import create_draft
from src.matcher import evaluate_match
from src.parser import parse_job_description

console = Console()


def read_profile() -> str:
    if not PROFILE_PATH.exists():
        console.print(f"[red]Profile not found at {PROFILE_PATH}[/red]")
        sys.exit(1)
    return PROFILE_PATH.read_text(encoding="utf-8")


def get_job_input() -> str:
    console.print(
        Panel(
            "Paste the job description text, or enter a path to a .txt file.\n"
            "For pasted text, finish with a line containing only 'END'.",
            title="JobAgent — Job Input",
        )
    )
    first_line = Prompt.ask("Enter file path, or press Enter to paste text")
    if first_line.strip():
        try:
            with open(first_line.strip(), "r", encoding="utf-8") as f:
                return f.read()
        except OSError as e:
            console.print(f"[red]Could not read file: {e}[/red]")
            sys.exit(1)

    lines: list[str] = []
    console.print("[dim]Paste job description, then a line with just 'END':[/dim]")
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == "END":
            break
        lines.append(line)
    return "\n".join(lines)


def main() -> None:
    console.rule("[bold cyan]JobAgent[/bold cyan]")

    raw_text = get_job_input()
    if not raw_text.strip():
        console.print("[red]No job description provided. Exiting.[/red]")
        sys.exit(1)

    with console.status("[bold]Parsing job description..."):
        job = parse_job_description(raw_text)

    console.print(
        Panel(
            f"[bold]{job.job_title}[/bold] @ [bold]{job.company_name}[/bold]\n"
            f"Recruiter: {job.recruiter_name or 'N/A'} <{job.recruiter_email or 'N/A'}>\n"
            f"Tech stack: {', '.join(job.tech_stack) or 'N/A'}",
            title="Parsed Job",
        )
    )

    existing = storage.find_existing(job.company_name, job.job_title)
    if existing:
        console.print(
            f"[yellow]This job (same company + title) was already processed on "
            f"{existing.get('timestamp')} — score {existing.get('match_score')}%, "
            f"status: {existing.get('draft_status')}.[/yellow]"
        )
        if not Confirm.ask("Process it again anyway?", default=False):
            console.print("Skipping. Exiting.")
            return

    profile_markdown = read_profile()

    with console.status("[bold]Evaluating match against your profile..."):
        match = evaluate_match(job, profile_markdown)

    table = Table(title="Match Result")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Match score", f"{match.match_score}%")
    table.add_row("Aligned", "Yes" if match.is_aligned else "No")
    table.add_row("Strengths", "\n".join(match.matching_strengths) or "N/A")
    table.add_row("Gaps", "\n".join(match.missing_or_gap_skills) or "N/A")
    table.add_row("Verdict", match.verdict_summary)
    console.print(table)

    if not match.is_aligned:
        proceed = Confirm.ask(
            f"[yellow]Role mismatch detected ({match.match_score}%). "
            "Do you still want to generate an application?[/yellow]",
            default=False,
        )
        if not proceed:
            storage.append_entry(
                company=job.company_name,
                title=job.job_title,
                match_score=match.match_score,
                is_aligned=match.is_aligned,
                draft_status="skipped_mismatch",
            )
            console.print("Logged as skipped. Exiting.")
            return

    with console.status("[bold]Drafting cold outreach email..."):
        email = draft_email(job, match, profile_markdown)

    console.print(
        Panel(
            f"[bold]To:[/bold] {email.recipient_email}\n"
            f"[bold]Subject:[/bold] {email.subject_line}\n\n{email.body}",
            title="Generated Email Draft",
        )
    )

    if not Confirm.ask("Save this as an unread draft in Gmail?", default=True):
        storage.append_entry(
            company=job.company_name,
            title=job.job_title,
            match_score=match.match_score,
            is_aligned=match.is_aligned,
            draft_status="draft_not_saved",
        )
        console.print("Not saved. Logged entry. Exiting.")
        return

    try:
        with console.status("[bold]Saving draft to Gmail..."):
            draft_id = create_draft(email)
    except RuntimeError as e:
        console.print(f"[red]Failed to save Gmail draft: {e}[/red]")
        storage.append_entry(
            company=job.company_name,
            title=job.job_title,
            match_score=match.match_score,
            is_aligned=match.is_aligned,
            draft_status="draft_failed",
        )
        sys.exit(1)

    storage.append_entry(
        company=job.company_name,
        title=job.job_title,
        match_score=match.match_score,
        is_aligned=match.is_aligned,
        draft_status="draft_created",
        draft_id=draft_id,
    )
    console.print(f"[green]Draft created in Gmail (id: {draft_id}).[/green]")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted. Exiting.[/yellow]")
        sys.exit(130)
