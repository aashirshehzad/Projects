"""Rich terminal rendering: severity-coloured tables and patch previews."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from app.llm_remediation.schemas import AuditRemediationReport
from app.static_scanner.ast_rules import Severity, Violation
from app.static_scanner.engine import ScanResult

_SEVERITY_STYLE = {
    Severity.CRITICAL: "bold white on red",
    Severity.HIGH: "bold red",
    Severity.MEDIUM: "yellow",
    Severity.LOW: "cyan",
}

console = Console()


def _sev_text(sev: Severity) -> Text:
    return Text(f" {sev.value} ", style=_SEVERITY_STYLE[sev])


def render_scan_summary(result: ScanResult) -> None:
    counts = result.counts_by_severity()
    header = (
        f"Scanned {result.files_scanned} file(s), "
        f"skipped {result.files_skipped}, "
        f"{len(result.violations)} violation(s)"
    )
    if result.ok:
        console.print(Panel(f"[bold green]PASS[/]  {header}", border_style="green"))
        return

    table = Table(title="Static AST Findings", header_style="bold magenta", expand=True)
    table.add_column("Sev", no_wrap=True)
    table.add_column("Rule", no_wrap=True)
    table.add_column("Location", no_wrap=True, style="cyan")
    table.add_column("Finding")
    for v in result.violations:
        finding = v.message
        if getattr(v, "tainted", False):
            finding = "[bold]\\[user input][/] " + finding
        table.add_row(
            _sev_text(v.severity),
            v.rule_id,
            f"{v.file_path}:{v.line_number}",
            finding,
        )
    console.print(table)
    tally = "  ".join(f"{k}={v}" for k, v in counts.items() if v)
    console.print(Panel(f"[bold red]FAIL[/]  {header}\n{tally}", border_style="red"))


def render_report(result: ScanResult, report: AuditRemediationReport) -> None:
    render_scan_summary(result)
    if not report.remediations:
        return

    console.rule("[bold]LLM Remediation")
    console.print(Panel(report.summary, title="Executive Summary", border_style="blue"))

    by_loc = {(v.file_path, v.line_number, v.rule_id): v for v in result.violations}
    for r in report.remediations:
        verdict = (
            "[bold red]EXPLOITABLE[/]"
            if r.is_exploitable
            else "[bold green]FALSE POSITIVE[/]"
        )
        console.print()
        console.print(
            f"{verdict}  [cyan]{r.file_path}:{r.line_number}[/]  ({r.rule_id})"
        )
        console.print(Text(r.root_cause, style="dim"))
        if r.is_exploitable and r.patched_code.strip():
            console.print(
                Panel(
                    Syntax(r.patched_code, "python", theme="ansi_dark", word_wrap=True),
                    title="Suggested patch",
                    border_style="green",
                )
            )
        if r.is_exploitable and r.unit_test.strip():
            console.print(
                Panel(
                    Syntax(r.unit_test, "python", theme="ansi_dark", word_wrap=True),
                    title="Regression test",
                    border_style="magenta",
                )
            )
