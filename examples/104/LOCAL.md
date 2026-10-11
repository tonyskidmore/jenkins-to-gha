# Example 104: local twin of example 004

Derived from [example 004](../004/README.md) (EclipseFdn/open-vsx.org, `Jenkinsfile` at `4d48d2d`). The original
is kept verbatim in `examples/004/`; this copy is edited only as far as needed for the pipeline to run to completion
in the harness. Every edit is marked `# j2gha-local:` in the Jenkinsfile.

| Lines | Original | Edit | Why | Feature kept? |
|---|---|---|---|---|
| 77 | `docker build --pull -t ${IMAGE_NAME}:${IMAGE_TAG} .` | the same line behind `echo` | no Docker daemon in the harness (and the final stage of the upstream Dockerfile pulls `ghcr.io/eclipse-openvsx/openvsx-server-snapshot`) | the stage, its own `agent { label }` (a separate job) and the `${IMAGE_TAG}` expansion |
| 89 | `docker push ...` | behind `echo` | no registry credentials | `withDockerRegistry` wrapper and stage |
| 103, 118, 133 | `./kubernetes/helm-deploy.sh <env> "${IMAGE_TAG}"` | behind `echo` | no OKD cluster | `when { branch }`, `container('kubectl')`, `withKubeConfig` |
| 154-155, 175-176 | `aws eks update-kubeconfig ...` and the helm deploy | behind `echo` | no AWS account or EKS cluster | `when { branch }`, `container('eks')`, `withCredentials` with two string credentials |

Deliberately **not** edited: the `environment {}` block (lines 48-63). Its `IMAGE_TAG = sh(...)` script branches
on `"${env.TAG_NAME}" = ""`, and the full-mode sweep found the two sides taking different branches (Jenkins renders
an unset `env.TAG_NAME` as the string `null`; the converted workflow set it to the empty string and ran
`printf -57`, which bash's `printf` rejects). That is a conversion gap, not a pipeline problem, so the line stays
as the test of the fix (`${TAG_NAME:-null}` in the converted step). Also unchanged: the Kubernetes pod agent (the
harness localises it to `agent any` and the converter maps it to a hosted runner), `options`, and the `post`
`failure`/`fixed` mails and `cleanup`.

Scenario: `uv run j2gha run 104 --tier jenkins,act --mode full --branch aws-main` (the repository's default branch,
so *Deploy aws-staging* runs and the other four deploy stages are skipped on both sides).
