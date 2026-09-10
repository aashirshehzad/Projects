"""Hybrid Code Auditor & Remediation Engine.

Two-stage pipeline:

* Stage 1-2  -- deterministic AST static scanner (local CPU, zero cost).
* Stage 3    -- single-call structured-JSON LLM remediation for real violations.
* Stage 4    -- dispatch to console / GitHub PR / SARIF.
"""

__version__ = "1.0.0"
