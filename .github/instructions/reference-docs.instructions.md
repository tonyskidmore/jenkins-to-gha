---
description: "The version-pinned Jenkins and GitHub Actions reference-docs bundles and the crosswalk"
applyTo: "j2gha/docs/**,j2gha/rules/docs-xref.yaml"
paths:
  - "j2gha/docs/**"
  - "j2gha/rules/docs-xref.yaml"
---
# Reference docs

- Bundles are fetched into `.docs/` or `$J2GHA_DOCS_DIR` and never committed. Labels are validated (never a path); a
  fetch builds in a staging dir and swaps it in, so a failure keeps the old bundle; `--parts` merges.
- Jenkins bundles are labelled `<core>+p<plugin-set digest>`.
- The harness never reads them. The migration report's Reference section uses `xref.web_refs()` (web URLs only, fixed
  to GitHub.com), so committed reports don't depend on what is downloaded.
- docs.github.com returns 429 on bursts, so the fetcher is sequential and caches raw pages in `.docs/.src/`.
- Every GHA page named in `j2gha/rules/docs-xref.yaml` must exist in `tests/fixtures/gha-pagelist-fpt.txt`; refresh
  that snapshot when GitHub reorganises its docs.
- `docs fetch` refuses to run with `J2GHA_OFFLINE=1`.

Reference: [docs/documentation.md](../../docs/documentation.md).
