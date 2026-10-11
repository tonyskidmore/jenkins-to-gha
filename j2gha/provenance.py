"""Content hashes tying each stage's artifacts to the inputs they were made from.

analyze stamps the parsed AST and analysis.json with the Jenkinsfile's hash, convert stamps conversion.json with the
Jenkinsfile and workflow-model hashes, and run records carry both plus the scenario. A later stage compares them
with the current inputs and refuses (or redoes) work built on stale ones instead of mixing versions.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_json(data: Any) -> str:
    return sha256_text(json.dumps(data, sort_keys=True, default=str))


def jenkinsfile_sha256(d: Path) -> str | None:
    f = d / "Jenkinsfile"
    return sha256_text(f.read_text()) if f.exists() else None
