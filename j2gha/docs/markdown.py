"""HTML -> Markdown helpers shared by the documentation fetchers."""

from __future__ import annotations

import re

_BLANKS = re.compile(r"\n[ \t]*\n(?:[ \t]*\n)+")
_TRAILING = re.compile(r"[ \t]+\n")
_PAD = re.compile(r"[ \t]{2,}")
_DASHES = re.compile(r"-{4,}")


def html_to_md(html: str) -> str:
    """Convert an HTML fragment to compact GitHub-flavoured Markdown."""
    from markdownify import markdownify

    text = markdownify(html, heading_style="ATX", bullets="-", code_language="", escape_underscores=False,
                       escape_asterisks=False)
    return tidy(text)


def tidy(text: str) -> str:
    """Normalise whitespace: strip trailing blanks, collapse blank-line runs, dedent stray indentation."""
    text = _TRAILING.sub("\n", text.replace("\r\n", "\n").replace(" ", " "))
    lines = []
    in_code = False
    for line in text.split("\n"):
        if line.lstrip().startswith("```"):
            in_code = not in_code
            lines.append(line.strip())
            continue
        if not in_code and line.lstrip().startswith("|"):
            # Table cells padded for display cost tokens and nothing else: "|  a   | :----- |" -> "| a | :--- |"
            line = _DASHES.sub("---", _PAD.sub(" ", line.strip()))
        # Jenkins help HTML is hand-indented; leading spaces would turn prose into code blocks.
        lines.append(line if in_code or line.lstrip().startswith(("-", "*", "|")) else line.strip())
    return _BLANKS.sub("\n\n", "\n".join(lines)).strip() + "\n"


def indent(text: str, prefix: str = "  ") -> str:
    return "\n".join(prefix + line if line else line for line in text.strip("\n").rstrip().split("\n"))


def slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-") or "page"
