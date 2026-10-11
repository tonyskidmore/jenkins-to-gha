"""Small AsciiDoc -> Markdown converter for jenkins.io sources.

Covers what the jenkins.io handbook and the reports.jenkins.io step references actually use: front matter,
section titles, listing/literal/example/sidebar/passthrough blocks (``++++`` HTML is converted with markdownify),
``[source,lang]``, admonitions, lists, definition lists, and the inline ``link:``/``plugin:``/``<<xref>>`` macros.
Tables are left in AsciiDoc ``|===`` form, which models read fine. No system dependencies (pandoc < 3.8.3 cannot
read AsciiDoc, and asciidoctor needs Ruby).
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from .markdown import html_to_md, tidy

SITE = "https://www.jenkins.io"

_FRONT = re.compile(r"\A---\n(.*?)\n---\n", re.S)
_TITLE = re.compile(r'^title:\s*"?(.*?)"?\s*$', re.M)
_ATTR = re.compile(r"^:([\w-]+!?):\s*(.*)$")
_HEADING = re.compile(r"^(={1,6})\s+(.*)$")
_BLOCK_ATTR = re.compile(r"^\[(.*)\]$")
_DELIM = {"----": "listing", "....": "literal", "====": "example", "****": "sidebar", "++++": "pass",
          "____": "quote", "--": "open"}
_SKIP_MACRO = re.compile(r"^(image|video|include|toc|ifdef|ifndef|ifeval|endif)::.*$")
_ADMONITION = re.compile(r"^(NOTE|TIP|IMPORTANT|WARNING|CAUTION|XXX):\s+(.*)$")


def _inline(line: str, page_url: str) -> str:
    def link(m: re.Match) -> str:
        target, text = m.group(1), m.group(2) or m.group(1)
        if not re.match(r"[a-z]+:", target):
            target = urljoin(page_url, target)
        return f"[{text.split(',')[0].strip(chr(34))}]({target})"

    line = re.sub(r"link:(\S+?)\[([^\]]*)\]", link, line)
    line = re.sub(r"(?<![(\[])\b(https?://[^\s\[\]]+)\[([^\]]*)\]", lambda m: f"[{m.group(2) or m.group(1)}]({m.group(1)})",
                  line)
    line = re.sub(r"plugin:([\w.-]+)\[([^\]]*)\]",
                  lambda m: f"[{m.group(2) or m.group(1)}](https://plugins.jenkins.io/{m.group(1)})", line)

    def xref(m: re.Match) -> str:
        target, _, text = m.group(1).partition(",")
        if "#" not in target:  # <<anchor>> is in-page
            return f"[{(text or target).strip()}](#{target.strip()})"
        doc, _, anchor = target.partition("#")
        url = urljoin(page_url, f"../{doc.strip()}/") if doc.strip() else ""
        return f"[{(text or anchor or doc).strip()}]({url}#{anchor})"

    line = re.sub(r"<<([^>]+)>>", xref, line)
    line = re.sub(r"(?<![\w*])\*([^*\s][^*]*?)\*(?![\w*])", r"**\1**", line)  # *bold* -> **bold**
    line = re.sub(r"(?<![\w+])\+([^+\s][^+]*?)\+(?![\w+])", r"`\1`", line)  # +mono+ -> `mono`
    line = re.sub(r"\{empty\}", "", line)
    return line


def adoc_to_md(text: str, page_url: str = SITE) -> tuple[str, str]:
    """Return (title, markdown)."""
    title = ""
    m = _FRONT.match(text)
    if m:
        t = _TITLE.search(m.group(1))
        title = t.group(1) if t else ""
        text = text[m.end():]
    attrs: dict[str, str] = {}
    out: list[str] = []
    lang = ""
    block: str | None = None
    block_delim = ""
    buf: list[str] = []
    for raw in text.split("\n"):
        line = raw.rstrip()
        if block is not None:
            if line == block_delim:
                if block == "pass":
                    out.append(html_to_md("\n".join(buf)))
                elif block in ("listing", "literal"):
                    out += [f"```{lang}", *buf, "```"]
                block, buf, lang = None, [], ""
            else:
                buf.append(raw)
            continue
        if line in _DELIM:
            if _DELIM[line] in ("listing", "literal", "pass"):
                block, block_delim = _DELIM[line], line
            continue  # example/sidebar/quote/open delimiters: keep the content, drop the frame
        a = _ATTR.match(line)
        if a:
            attrs[a.group(1)] = a.group(2)
            continue
        if _SKIP_MACRO.match(line) or line.startswith("//"):
            continue
        b = _BLOCK_ATTR.match(line)
        if b:
            spec = b.group(1)
            if spec.startswith(("source", "pipeline")) or spec in ("source",):
                parts = [p.strip() for p in spec.split(",")]
                lang = parts[1] if len(parts) > 1 and parts[0] == "source" else ("groovy" if parts[0] == "pipeline" else "")
            elif spec.startswith("[") and spec.endswith("]"):  # [[anchor]]
                out.append(f'<a id="{spec[1:-1].split(",")[0]}"></a>')
            continue
        h = _HEADING.match(line)
        if h:
            level = len(h.group(1))
            if not title and level == 1:
                title = h.group(2)
            out.append("#" * level + " " + _inline(h.group(2), page_url))
            continue
        ad = _ADMONITION.match(line)
        if ad:
            out.append(f"> **{ad.group(1).title()}:** {_inline(ad.group(2), page_url)}")
            continue
        if line == "+":  # list continuation
            out.append("")
            continue
        lm = re.match(r"^(\*{1,5}|\.{1,5})\s+(.*)$", line)
        if lm:
            depth = len(lm.group(1)) - 1
            marker = "-" if lm.group(1)[0] == "*" else "1."
            out.append("  " * depth + f"{marker} {_inline(lm.group(2), page_url)}")
            continue
        dl = re.match(r"^(\S.*?)(:{2,4})\s*(.*)$", line)
        if dl and not re.match(r"^[a-z]+://", line) and " " not in dl.group(1).strip("`"):
            out.append(f"- **{_inline(dl.group(1), page_url)}**" + (f": {_inline(dl.group(3), page_url)}"
                                                                    if dl.group(3) else ""))
            continue
        for k, v in attrs.items():
            line = line.replace("{" + k + "}", v)
        out.append(_inline(line, page_url))
    return title, tidy("\n".join(out))


def report_sections(text: str) -> tuple[str, list[tuple[str, str]]]:
    """Split a reports.jenkins.io step/directive ``.adoc`` (headings + raw HTML, ``++++`` optional) into
    ``(title, [(heading, markdown), ...])`` - one entry per ``=== `symbol`: description`` section."""
    title = ""
    m = _FRONT.match(text)
    if m:
        t = _TITLE.search(m.group(1))
        title = t.group(1) if t else ""
        text = text[m.end():]
    sections: list[tuple[str, str]] = []
    heading, prelude, html = "", [], []

    def flush() -> None:
        body = "\n".join(prelude) + ("\n\n" + html_to_md("\n".join(html)) if html else "")
        if heading or body.strip():
            sections.append((heading, tidy(body)))

    for raw in text.split("\n"):
        line = raw.rstrip()
        if _ATTR.match(line) or line == "++++":
            continue
        h = re.match(r"^(={2,3})\s+(.*)$", line)
        if h:
            flush()
            heading, prelude, html = _inline(h.group(2), SITE), [], []
            continue
        if line.startswith("plugin:"):
            prelude.append(_inline(line, SITE))
        else:
            html.append(raw)
    flush()
    return title, sections
