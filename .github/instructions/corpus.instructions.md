---
description: "The example corpus: cited originals, twins, the walkthrough, licences and generated results"
applyTo: "examples/**,THIRD-PARTY-NOTICES.md"
paths:
  - "examples/**"
  - "THIRD-PARTY-NOTICES.md"
---
# The corpus (`examples/`)

- **Originals** `examples/0NN` are cited real-world Jenkinsfiles: never edit their `Jenkinsfile`. Crawled ids stay
  below 100.
- **Twins** `examples/1NN` are minimally edited copies that run to completion, every edit listed in `LOCAL.md`
  (skill `jenkins-example-twin`).
- **The walkthrough** `examples/000` is a hand-written tutorial: only `README.md` and `Jenkinsfile` are tracked. Its
  README carries `<!-- j2gha:walkthrough -->`, so stages write to a gitignored `RESULTS.md`, and `all`, `summary` and
  the crawler skip it. Re-run it end to end after generator or localiser changes.
- **Licences:** each crawled example carries `LICENSE.upstream` (and `NOTICE.upstream` where the source has one),
  listed in `THIRD-PARTY-NOTICES.md`. The crawler does not write these yet: add them, and the table row, by hand. The
  crawler does not exclude copyleft licences (AGPL sources were dropped, 2026-10-11): check a new example's licence
  with the user before keeping it.
- **Generated, not hand-edited:** examples' `analysis/`, `gha/`, `runs/`, their README sections and
  `examples/README.md` (`uv run j2gha summary`).
  - Gitignored: `runs/**/workspace/`, `runs/*/artifacts/` (act's artifact store, up to about 110 MB a run).
  - Regenerate with `J2GHA_OFFLINE=1 uv run j2gha analyze all && ... convert all && ... validate all`: offline, action
    pins come only from the cache, so converted models, and with them the recorded runs, stay valid. Drop
    `validation.json` changes that are only the `validated_at` timestamp.
- **Users' own pipelines never belong here:** they live in `J2GHA_PIPELINES_DIR`, outside the clone.

Reference: [docs/results.md](../../docs/results.md), [docs/scoring.md](../../docs/scoring.md),
[THIRD-PARTY-NOTICES.md](../../THIRD-PARTY-NOTICES.md).
