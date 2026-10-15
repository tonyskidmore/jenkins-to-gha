---
description: "Harness Docker images: digest pins and the Jenkins plugin list"
applyTo: "docker/**"
paths:
  - "docker/**"
---
# Docker images

- Base images are digest-pinned in `docker/*/Dockerfile`; the Jenkins base is also in `config.JENKINS_BASE_IMAGE`
  (`j2gha/config.py`): change both together.
- Every plugin in `docker/jenkins/plugins.txt` is `name:version`. To add one: add the bare name, run
  `uv run j2gha docker build --only jenkins`, and paste the `+ name:version` lines the `j2gha-check-plugins` step
  prints.
- A Declarative agent, option, trigger or parameter type whose plugin is missing makes `toJson`/`validate` reject the
  pipeline: a false `JenkinsValidationFailed` finding. Adding the plugin is the fix.
- The runner images carry the Jenkins image's toolchain, so converted pipelines find the same tools on both sides.
- `docker/jenkins/groovy/*` (the AST dumper) is protected for rule-improvement changes; `plugins.txt` and the Jenkins
  `Dockerfile` need a human review (`evals/protected.txt`).

Reference: [docs/prerequisites.md](../../docs/prerequisites.md), [docs/extending.md](../../docs/extending.md).
