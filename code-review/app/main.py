"""Click CLI entry point.

Commands
--------
* ``audit <path>``        -- full recursive scan (+ optional LLM remediation).
* ``diff <base-branch>``  -- scan only lines changed since the merge base.
* ``fix <path>``          -- scan, remediate, and optionally write patches locally.

Exit codes: ``0`` clean, ``1`` findings, ``2`` operational error.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from app import __version__
from app.core.config import get_settings
from app.core.exceptions import AuditorError
from app.llm_remediation.remediator import Remediator, build_unreviewed_report
from app.llm_remediation.schemas import AuditRemediationReport
from app.reporter.console import console, render_report, render_scan_summary
from app.reporter.sarif import write_sarif
from app.static_scanner.ast_rules import Severity
from app.static_scanner.diff_parser import (
    changed_line_map,
    changed_python_files,
    filter_to_diff,
)
from app.static_scanner.engine import ScanResult, scan_path, scan_paths

_EXIT_OK = 0
_EXIT_FINDINGS = 1
_EXIT_ERROR = 2


# --------------------------------------------------------------------------- #
# shared option groups
# --------------------------------------------------------------------------- #
def _llm_options(fn):
    fn = click.option("--no-llm", is_flag=True, help="Static findings only; skip Stage 3.")(fn)
    fn = click.option("--model", default=None, help="Override the remediation model id.")(fn)
    return fn


def _output_options(fn):
    fn = click.option(
        "--sarif", "sarif_path", type=click.Path(dir_okay=False), default=None,
        help="Write a SARIF 2.1.0 file for code-scanning dashboards.",
    )(fn)
    fn = click.option(
        "--json", "json_path", type=click.Path(dir_okay=False), default=None,
        help="Write the full remediation report as JSON.",
    )(fn)
    fn = click.option(
        "--fail-on",
        type=click.Choice([s.value for s in Severity], case_sensitive=False),
        default="MEDIUM",
        show_default=True,
        help="Minimum severity that makes the run fail (exit 1).",
    )(fn)
    fn = click.option("--ci-mode", is_flag=True, help="Terser output; honour --fail-on strictly.")(fn)
    return fn


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _run_remediation(
    result: ScanResult, *, no_llm: bool, model: str | None
) -> AuditRemediationReport:
    if no_llm or not result.violations:
        return build_unreviewed_report(result.violations)
    settings = get_settings()
    if model:
        settings = settings.model_copy(update={"llm_model": model})
    try:
        return Remediator(settings=settings).remediate(result.violations)
    except AuditorError as exc:
        console.print(f"[yellow]LLM remediation unavailable:[/] {exc}")
        console.print("[yellow]Falling back to static-only report.[/]")
        return build_unreviewed_report(result.violations)


def _emit_outputs(
    result: ScanResult,
    report: AuditRemediationReport,
    *,
    sarif_path: str | None,
    json_path: str | None,
) -> None:
    if sarif_path:
        write_sarif(sarif_path, result, report)
        console.print(f"[dim]SARIF written to {sarif_path}[/]")
    if json_path:
        Path(json_path).write_text(report.model_dump_json(indent=2), encoding="utf-8")
        console.print(f"[dim]JSON report written to {json_path}[/]")


def _decide_exit(
    result: ScanResult, report: AuditRemediationReport, *, fail_on: str, ci_mode: bool
) -> int:
    threshold = Severity(fail_on.upper()).rank
    relevant = [v for v in result.violations if v.severity.rank <= threshold]
    if not relevant:
        return _EXIT_OK
    if ci_mode:
        # In CI a violation only fails the build if the LLM did not clear it.
        cleared = {
            (r.rule_id, r.file_path, r.line_number)
            for r in report.false_positives()
        }
        still_bad = [
            v for v in relevant
            if (v.rule_id, v.file_path, v.line_number) not in cleared
        ]
        return _EXIT_FINDINGS if still_bad else _EXIT_OK
    return _EXIT_FINDINGS


def _apply_patches(result: ScanResult, report: AuditRemediationReport, *, assume_yes: bool) -> int:
    """Rewrite local files with exploitable patches. Returns files changed."""
    # group remediations by file, applied bottom-up to keep line numbers valid
    by_file: dict[str, list] = {}
    loc = {(v.rule_id, v.file_path, v.line_number): v for v in result.violations}
    for r in report.remediations:
        v = loc.get((r.rule_id, r.file_path, r.line_number))
        if not r.is_exploitable or not r.patched_code.strip() or v is None:
            continue
        by_file.setdefault(r.file_path, []).append((v, r))

    changed = 0
    for file_path, items in by_file.items():
        path = Path(file_path)
        if not path.exists():
            console.print(f"[yellow]skip {file_path}: not found on disk[/]")
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        items.sort(key=lambda pair: pair[0].context_start_line, reverse=True)
        for v, r in items:
            start = v.context_start_line or v.line_number
            span = len((v.snippet or "").splitlines()) or 1
            end = start + span - 1
            current = "\n".join(lines[start - 1 : end])
            if v.snippet and current.strip() != v.snippet.strip():
                console.print(
                    f"[yellow]skip {file_path}:{start}: source drifted since scan[/]"
                )
                continue
            if not assume_yes and not click.confirm(
                f"Apply {r.rule_id} patch to {file_path}:{start}-{end}?", default=False
            ):
                continue
            lines[start - 1 : end] = r.patched_code.rstrip("\n").splitlines()
            changed += 1
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return changed


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="hybrid-code-auditor")
def cli() -> None:
    """Hybrid AST + single-call LLM code auditor."""


@cli.command()
@click.argument("path", type=click.Path(exists=True), default=".")
@_llm_options
@_output_options
@click.option("--github-pr-comments", is_flag=True, help="Post findings to the current PR.")
def audit(
    path: str,
    no_llm: bool,
    model: str | None,
    sarif_path: str | None,
    json_path: str | None,
    fail_on: str,
    ci_mode: bool,
    github_pr_comments: bool,
) -> None:
    """Recursively audit PATH (a file or directory)."""
    try:
        result = scan_path(path)
        report = _run_remediation(result, no_llm=no_llm, model=model)
        if ci_mode or no_llm:
            render_scan_summary(result)
        else:
            render_report(result, report)
        _emit_outputs(result, report, sarif_path=sarif_path, json_path=json_path)
        if github_pr_comments:
            _post_to_pr(result, report)
    except AuditorError as exc:
        console.print(f"[bold red]error:[/] {exc}")
        sys.exit(_EXIT_ERROR)
    sys.exit(_decide_exit(result, report, fail_on=fail_on, ci_mode=ci_mode))


@cli.command()
@click.argument("base_branch", default="origin/main")
@_llm_options
@_output_options
@click.option("--github-pr-comments", is_flag=True, help="Post findings to the current PR.")
@click.option("--repo-root", type=click.Path(exists=True, file_okay=False), default=".")
def diff(
    base_branch: str,
    no_llm: bool,
    model: str | None,
    sarif_path: str | None,
    json_path: str | None,
    fail_on: str,
    ci_mode: bool,
    github_pr_comments: bool,
    repo_root: str,
) -> None:
    """Audit only the lines changed since BASE_BRANCH (merge-base diff)."""
    try:
        changed_files = changed_python_files(base_branch, repo_root=repo_root)
        if not changed_files:
            console.print("[green]No changed Python files vs "
                          f"{base_branch}; nothing to audit.[/]")
            sys.exit(_EXIT_OK)
        targets = [Path(repo_root) / f for f in changed_files]
        result = scan_paths(targets, base_dir=repo_root)
        line_map = changed_line_map(base_branch, repo_root=repo_root)
        result.violations = filter_to_diff(result.violations, line_map)

        report = _run_remediation(result, no_llm=no_llm, model=model)
        if ci_mode or no_llm:
            render_scan_summary(result)
        else:
            render_report(result, report)
        _emit_outputs(result, report, sarif_path=sarif_path, json_path=json_path)
        if github_pr_comments:
            _post_to_pr(result, report)
    except AuditorError as exc:
        console.print(f"[bold red]error:[/] {exc}")
        sys.exit(_EXIT_ERROR)
    sys.exit(_decide_exit(result, report, fail_on=fail_on, ci_mode=ci_mode))


@cli.command()
@click.argument("path", type=click.Path(exists=True))
@_llm_options
@click.option("--auto-apply", is_flag=True, help="Write patches into local files.")
@click.option("--yes", "assume_yes", is_flag=True, help="Do not prompt before each patch.")
def fix(
    path: str,
    no_llm: bool,
    model: str | None,
    auto_apply: bool,
    assume_yes: bool,
) -> None:
    """Audit PATH and (with --auto-apply) patch the source in place."""
    if no_llm:
        raise click.UsageError("`fix` needs the LLM stage; drop --no-llm.")
    try:
        result = scan_path(path)
        report = _run_remediation(result, no_llm=False, model=model)
        render_report(result, report)
        if not auto_apply:
            console.print("\n[dim]Re-run with --auto-apply to write these patches.[/]")
            sys.exit(_EXIT_FINDINGS if result.violations else _EXIT_OK)
        changed = _apply_patches(result, report, assume_yes=assume_yes)
        console.print(f"\n[bold green]Patched {changed} location(s).[/]")
    except AuditorError as exc:
        console.print(f"[bold red]error:[/] {exc}")
        sys.exit(_EXIT_ERROR)
    sys.exit(_EXIT_OK if not result.violations else _EXIT_FINDINGS)


def _post_to_pr(result: ScanResult, report: AuditRemediationReport) -> None:
    from app.reporter.github_pr import GitHubPRReporter

    reporter = GitHubPRReporter()
    posted = reporter.post_inline_comments(result, report)
    reporter.post_summary(result, report)
    console.print(f"[dim]Posted {posted} inline comment(s) + summary to PR.[/]")


if __name__ == "__main__":  # pragma: no cover
    cli()
