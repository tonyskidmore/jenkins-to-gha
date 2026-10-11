"""Search plan for locating different Jenkins pipeline styles on github.com (legacy /search/code syntax).

Notes on legacy code search: punctuation is ignored (``"@Library"`` == ``Library``), only default branches
and files < 384 KB are indexed, max 1000 results per query, 10 requests/minute. ``size:`` ranges are used to
skew results away from trivial files.
"""

from __future__ import annotations

import re

# Ordered by selection priority: the crawler round-robins over these when choosing examples.
STYLE_QUERIES: dict[str, list[str]] = {
    "declarative": [
        'filename:Jenkinsfile pipeline agent stages steps size:800..4000',
    ],
    "scripted": [
        'filename:Jenkinsfile node stage checkout scm NOT pipeline size:600..6000',
    ],
    "matrix": [
        'filename:Jenkinsfile matrix axes axis',
    ],
    "parallel": [
        'filename:Jenkinsfile parallel failFast pipeline stages',
    ],
    "docker-agent": [
        'filename:Jenkinsfile agent docker image reuseNode',
        'filename:Jenkinsfile agent dockerfile filename',
    ],
    "kubernetes-agent": [
        'filename:Jenkinsfile agent kubernetes yaml containers',
        'filename:Jenkinsfile podTemplate containerTemplate',
    ],
    "shared-library": [
        'filename:Jenkinsfile "@Library" pipeline',
    ],
    "library-template": [
        'path:vars extension:groovy "def call" pipeline agent stages',
    ],
    "when-post": [
        'filename:Jenkinsfile when branch post always failure success size:1500..8000',
    ],
    "input-gate": [
        'filename:Jenkinsfile input message submitter pipeline',
    ],
    "credentials": [
        'filename:Jenkinsfile withCredentials usernamePassword pipeline',
    ],
    "parameters-triggers": [
        'filename:Jenkinsfile parameters booleanParam choice triggers cron',
    ],
    "artifacts-tests": [
        'filename:Jenkinsfile stash unstash junit archiveArtifacts',
    ],
    "downstream-build": [
        'filename:Jenkinsfile "build job" wait propagate',
    ],
    "dynamic-groovy": [
        'filename:Jenkinsfile parallel collectEntries',
        'filename:Jenkinsfile load groovy script def',
    ],
    "windows": [
        'filename:Jenkinsfile bat powershell agent label windows',
    ],
    "tools": [
        'filename:Jenkinsfile tools maven jdk pipeline',
    ],
}

# Constructs that make an example particularly valuable for a migration test corpus.
SHOWCASE_STYLES = {"matrix", "dynamic-groovy", "input-gate", "library-template", "kubernetes-agent",
                   "downstream-build", "windows"}

SKIP_PATH_PARTS = ("node_modules/", "vendor/", "/testdata/", "/test-data/", "/fixtures/", "test/resources/", "src/test/",
                   "data/valid/", "data/invalid/")

# Owner crawls (``--owner``) walk repository trees instead of code search, which misses archived repositories and
# names like ``jenkinsfile.groovy`` or ``jenkinsfiles/jenkinsfile-publish``. A path is a candidate when its basename
# mentions Jenkinsfile, or it is a ``.groovy``/``.jenkins`` script outside a library's ``src/`` classes; its content
# must then look like a pipeline.
PIPELINE_NAME_RE = re.compile(r"(?i)jenkinsfile")
PIPELINE_EXT_RE = re.compile(r"(?i)\.(groovy|jenkins)$")
PIPELINE_HINT_RE = re.compile(r"\bpipeline\s*\{|\bnode\s*[({]|\bstage\s*\(|\bpodTemplate\s*\(")


def is_pipeline_path(path: str) -> bool:
    if any(part in f"/{path}" for part in SKIP_PATH_PARTS):
        return False
    base = path.rsplit("/", 1)[-1]
    if PIPELINE_NAME_RE.search(base):
        return True
    return bool(PIPELINE_EXT_RE.search(base)) and not path.startswith("src/") and "/src/" not in path
