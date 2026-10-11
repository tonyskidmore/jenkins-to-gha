"""Local, version-pinned Jenkins and GitHub Actions reference documentation for agents.

The docs are downloaded on demand (``j2gha docs fetch``) into a gitignored directory (``.docs/`` or
``$J2GHA_DOCS_DIR``) as one Markdown file per page plus an llms.txt-style ``INDEX.md`` per bundle, so agents can
grep and read them without network access. Nothing here is committed: the repository only holds the fetchers.
"""
