"""Extract pinned ``(name, version)`` pairs from Python dependency manifests.

Only *exact* pins can be checked against an advisory database, so ranges
(``>=``, ``~=``, ``^``) are skipped. Supported: requirements*.txt, poetry.lock,
Pipfile.lock, uv.lock, and ``==`` entries in pyproject.toml.
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

_REQ_LINE = re.compile(
    r"^\s*(?P<name>[A-Za-z0-9._-]+)\s*(?:\[[^\]]+\])?\s*===?\s*"
    r"(?P<version>[A-Za-z0-9._*+!-]+)"
)
_MANIFEST_GLOBS = (
    "requirements.txt",
    "requirements-*.txt",
    "requirements/*.txt",
    "requirements*.txt",
    "poetry.lock",
    "Pipfile.lock",
    "uv.lock",
    "pyproject.toml",
)


@dataclass(frozen=True, slots=True)
class Requirement:
    name: str          # PEP 503 normalised
    version: str
    manifest: str      # path relative to the scanned root
    line_number: int   # 1-based; 0 when the format has no meaningful line

    @property
    def raw(self) -> str:
        return f"{self.name}=={self.version}"


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower().strip()


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return path.name


# --------------------------------------------------------------------------- #
# per-format parsers
# --------------------------------------------------------------------------- #
def _parse_requirements(text: str, manifest: str) -> list[Requirement]:
    out: list[Requirement] = []
    # join backslash line-continuations, tracking the first physical line number
    logical: list[tuple[int, str]] = []
    buf, start = "", 0
    for i, physical in enumerate(text.splitlines(), start=1):
        if not buf:
            start = i
        stripped = physical.rstrip()
        if stripped.endswith("\\"):
            buf += stripped[:-1] + " "
            continue
        logical.append((start, buf + stripped))
        buf = ""
    if buf:
        logical.append((start, buf))

    for lineno, line in logical:
        code = line.split(" #", 1)[0].strip()
        if not code or code.startswith(("#", "-", "git+", "http://", "https://")):
            continue
        code = code.split(";", 1)[0].strip()          # drop env markers
        code = code.split("--hash", 1)[0].strip()
        m = _REQ_LINE.match(code)
        if not m or "*" in m.group("version"):
            continue
        out.append(
            Requirement(normalize(m.group("name")), m.group("version"), manifest, lineno)
        )
    return out


def _parse_poetry_lock(text: str, manifest: str) -> list[Requirement]:
    try:
        data = tomllib.loads(text)
    except (tomllib.TOMLDecodeError, ValueError):
        return []
    rows = text.splitlines()
    out: list[Requirement] = []
    for pkg in data.get("package", []):
        name, version = pkg.get("name"), pkg.get("version")
        if not name or not version:
            continue
        lineno = next(
            (n for n, r in enumerate(rows, 1) if r.strip() == f'name = "{name}"'), 0
        )
        out.append(Requirement(normalize(name), str(version), manifest, lineno))
    return out


def _parse_pipfile_lock(text: str, manifest: str) -> list[Requirement]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    out: list[Requirement] = []
    for section in ("default", "develop"):
        for name, spec in (data.get(section) or {}).items():
            ver = (spec or {}).get("version", "") if isinstance(spec, dict) else ""
            if ver.startswith("=="):
                out.append(Requirement(normalize(name), ver[2:], manifest, 0))
    return out


def _parse_uv_lock(text: str, manifest: str) -> list[Requirement]:
    try:
        data = tomllib.loads(text)
    except (tomllib.TOMLDecodeError, ValueError):
        return []
    out: list[Requirement] = []
    for pkg in data.get("package", []):
        name, version = pkg.get("name"), pkg.get("version")
        if name and version:
            out.append(Requirement(normalize(name), str(version), manifest, 0))
    return out


def _parse_pyproject(text: str, manifest: str) -> list[Requirement]:
    try:
        data = tomllib.loads(text)
    except (tomllib.TOMLDecodeError, ValueError):
        return []
    out: list[Requirement] = []
    for dep in (data.get("project") or {}).get("dependencies", []) or []:
        m = _REQ_LINE.match(dep.split(";", 1)[0].strip())
        if m and "*" not in m.group("version"):
            out.append(
                Requirement(normalize(m.group("name")), m.group("version"), manifest, 0)
            )
    return out


_DISPATCH = {
    "poetry.lock": _parse_poetry_lock,
    "Pipfile.lock": _parse_pipfile_lock,
    "uv.lock": _parse_uv_lock,
    "pyproject.toml": _parse_pyproject,
}


def parse_manifest(path: Path, root: Path) -> list[Requirement]:
    manifest = _rel(path, root)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    parser = _DISPATCH.get(path.name)
    if parser is None and path.name.endswith(".txt") and "requirement" in path.name.lower():
        parser = _parse_requirements
    if parser is None:
        return []
    return parser(text, manifest)


def discover(root: str | Path) -> list[Requirement]:
    """All pinned requirements found under *root*, de-duplicated by (name, version)."""
    root = Path(root)
    if root.is_file():
        root, files = root.parent, [root]
    else:
        files = []
        for pattern in _MANIFEST_GLOBS:
            files.extend(sorted(root.glob(pattern)))

    seen: set[tuple[str, str]] = set()
    reqs: list[Requirement] = []
    for f in files:
        for req in parse_manifest(f, root):
            key = (req.name, req.version)
            if key in seen:
                continue
            seen.add(key)
            reqs.append(req)
    return reqs
