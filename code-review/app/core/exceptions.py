"""Custom domain exception classes.

Every failure mode in the pipeline maps to one of these so callers (and the CLI
exit-code handler) can react deterministically instead of catching bare
``Exception``.
"""

from __future__ import annotations


class AuditorError(Exception):
    """Base class for every error raised by this package."""


class ConfigurationError(AuditorError):
    """Missing or invalid configuration (e.g. no API key when LLM stage runs)."""


class GitDiffError(AuditorError):
    """``git`` was unavailable, not a repo, or produced an unparseable diff."""


class ScannerError(AuditorError):
    """A source file could not be parsed or walked by the static engine."""


class LLMRemediationError(AuditorError):
    """The remediation model call failed, timed out, or returned invalid JSON."""


class ReportingError(AuditorError):
    """A downstream sink (GitHub API, SARIF file) rejected the report."""
