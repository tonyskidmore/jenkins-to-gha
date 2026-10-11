"""LOCALIZER_VERSION must change whenever the localised scripts change.

Run records carry the localiser version as provenance and a Jenkins reference recorded by another version is refused
(execute.reference_problem). A localisation change that forgets the bump would let an earlier execution stand in for
different semantics (review R8-1), so the localised output of every fixture, in both modes and with representative
auto-repairs, is fingerprinted and recorded with the version it belongs to.

After a deliberate localisation change: bump LOCALIZER_VERSION (j2gha/jenkins/localize.py), then record the new
fingerprint with ``uv run python tests/test_localizer_version.py``.
"""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from j2gha.analysis.analyze import analyse  # noqa: E402
from j2gha.jenkins.localize import LOCALIZER_VERSION, localize  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
RECORD = FIXTURES / "LOCALIZER.sha256"
SOURCE = {"url": "https://github.com/example/project.git", "sha": "0123456789abcdef0123456789abcdef01234567"}
VARIANTS = [
    {"mode": "trace"},
    {"mode": "full", "source": SOURCE},
    {"mode": "full", "source": SOURCE, "docker": True},
    {"mode": "full", "source": SOURCE, "extra_stubs": ["libraryStep"],
     "remove": [("stub-property", "config"), ("options", "gitLabConnection"), ("fill-stage", "Build")]},
]


def fingerprint() -> str:
    h = hashlib.sha256()
    for src in sorted(FIXTURES.glob("Jenkinsfile.*")):
        name = src.name.split(".", 1)[1]
        ast_path = FIXTURES / f"{name}.ast.json"
        if not ast_path.exists():
            continue
        text, ast = src.read_text(), json.loads(ast_path.read_text())
        analysis = analyse(text, ast)
        for v in VARIANTS:
            h.update(f"{name} {json.dumps(v, sort_keys=True)}\n".encode())
            h.update(localize(text, ast, analysis, **v).script.encode())
    return h.hexdigest()


def test_localised_output_matches_the_recorded_version():
    version, digest = RECORD.read_text().split()
    current = fingerprint()
    assert int(version) == LOCALIZER_VERSION, (
        f"LOCALIZER_VERSION is {LOCALIZER_VERSION} but the fingerprint was recorded for v{version}: "
        "record it with `uv run python tests/test_localizer_version.py`")
    assert current == digest, (
        "the localised scripts changed but LOCALIZER_VERSION did not: bump it in j2gha/jenkins/localize.py "
        "(run records made by the old localiser must stop serving as references), then record the fingerprint "
        "with `uv run python tests/test_localizer_version.py`")


if __name__ == "__main__":
    RECORD.write_text(f"{LOCALIZER_VERSION} {fingerprint()}\n")
    print(RECORD.read_text().strip())
