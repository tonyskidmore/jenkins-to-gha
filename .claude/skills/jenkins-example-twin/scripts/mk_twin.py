"""Create examples/<dst> as a local twin of examples/<src>: Jenkinsfile copied (edit it afterwards), source.json with
the new id and a derived_from field, README rendered from it with the twin note. Run from the repo root:
    uv run python .claude/skills/jenkins-example-twin/scripts/mk_twin.py 009 109
"""
import json
import pathlib
import sys

from j2gha.analysis.analyze import STYLE_TITLES
from j2gha.readme import render_example_readme

src, dst = sys.argv[1], sys.argv[2]
s, d = pathlib.Path("examples") / src, pathlib.Path("examples") / dst
d.mkdir(exist_ok=False)
(d / "Jenkinsfile").write_text((s / "Jenkinsfile").read_text())
meta = json.loads((s / "source.json").read_text())
meta["id"] = dst
meta["derived_from"] = {"example": src,
                        "note": "Jenkinsfile edited so the pipeline runs to completion in the harness; see LOCAL.md"}
(d / "source.json").write_text(json.dumps(meta, indent=2) + "\n")
readme = render_example_readme(meta, STYLE_TITLES)
title, rest = readme.split("\n", 1)
note = (f"\n_Local twin of [example {src}](../{src}/README.md): the Jenkinsfile is **not** verbatim; its edits are "
        f"listed in\n[LOCAL.md](LOCAL.md). The citation below is the original file's._\n")
(d / "README.md").write_text(title + "\n" + note + rest)
print(f"examples/{dst} created from {src}; now edit examples/{dst}/Jenkinsfile and write LOCAL.md")
