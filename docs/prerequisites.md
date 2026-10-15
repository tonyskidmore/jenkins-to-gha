# Prerequisites

What you need depends on how far you go. Analysing, converting, validating and running pipelines locally needs Docker,
Python and uv; the GitHub tiers also need the GitHub CLI and a repository you administer.

| Requirement | Needed for | Notes |
|---|---|---|
| An x86-64 (amd64) Docker host: Linux, macOS or Windows with WSL2 | everything | Developed and tested on WSL2 (Ubuntu 22.04, x86_64); other hosts are untested. The self-hosted runner image selects a checksum-pinned Node download for either amd64 or arm64. The act CLI image still downloads an x86-64 binary and act runs jobs with `--container-architecture linux/amd64`, so native ARM support for the whole harness is not established; act on ARM hosts (Apple Silicon, ARM Linux) needs x86-64 emulation, which is untested and slow. |
| [Docker Engine](https://docs.docker.com/engine/install/), usable without `sudo` | every stage | Parses Jenkinsfiles with the Groovy inside the Jenkins image (`convert` skips this when an up-to-date analysis exists) and runs the Jenkins controller, act, actionlint, zizmor and the self-hosted runners. `uv run j2gha docker build` builds four images: `j2gha/jenkins:local`, `j2gha/act:local`, and the two runner images `j2gha/act-runner:local` and `j2gha/runner:local` (the upstream act and Actions runner images plus the Jenkins image's toolchain, so converted pipelines find the same Maven, Node, make and Python on both sides). It also pulls the pinned actionlint and zizmor images. The images take about 6.5 GB (Jenkins 1.7 GB, act runner 2.2 GB, Actions runner 2.3 GB, act and the two linters 0.3 GB); allow about **10 GB of disk** for the build cache, act's cache and run workspaces. Allow **4 GB of free memory**: the controller is capped at 3 GB. |
| Internet access | `docker build`, `crawl`, `convert` (SHA pinning), local runs, the GitHub tiers, `docs fetch` | The image build downloads base images (Docker Hub, ghcr.io), Jenkins plugins and the act release. Local runs need it too: act downloads each action the first time it is used, and full mode fetches the example's source repository and whatever its build downloads. `J2GHA_OFFLINE=1` stops the harness's own GitHub calls and fetches ([own-pipelines.md](own-pipelines.md#offline-mode)). |
| Python 3.10+ and [uv](https://docs.astral.sh/uv/getting-started/installation/) | everything | `uv sync` installs the harness into `.venv` (uv downloads a suitable Python if none is installed). The unit tests pass on 3.10 and 3.13. |
| git | everything | The remote GitHub tiers use the `origin` remote of your clone. |
| [GitHub CLI](https://cli.github.com/) (`gh`), logged in with the `repo` and `workflow` scopes | `crawl`, `--tier selfhosted`, `--tier hosted`, `budget`, `environments`; optional for `convert` | `gh auth login`, then check with `gh auth status`. The harness takes its token from `GH_TOKEN`, `GITHUB_TOKEN` or `gh auth token`. Without a token, `convert` still works but leaves actions on their version tags instead of pinning them to commit SHAs. |
| Billing access | `budget`, and `--tier hosted` on a private repository | Not needed when the target repository is public: standard GitHub-hosted runners are free there, so only the per-run cap applies. For a private repository you own: `gh auth refresh -h github.com -s user` (a fine-grained token needs *Plan: read*). For an organisation's repository: an owner or billing manager. Without complete billing data the guard refuses hosted runs (unless `J2GHA_ALLOW_INCOMPLETE_USAGE=1`, see the [walkthrough's Part 7.2](../examples/000/README.md#72-github-hosted-runners-spends-actions-minutes)). |
| A GitHub repository you administer, with Actions enabled | `--tier selfhosted` and `--tier hosted` | The `origin` of this clone, or `J2GHA_REPO=owner/repo`. Admin rights are needed to register just-in-time self-hosted runners and to create the `j2gha-*` environments (`--environments`). Throw-away `j2gha/run/...` branches are pushed and deleted again. |
| GitHub Actions minutes | `--tier hosted` only | Hosted runs on a private repository spend your allowance; check `uv run j2gha budget` first. `--tier selfhosted` uses no hosted-runner minutes. Both tiers upload artifacts (the workspace hand-off and archived files), which count towards the account's artifact storage (the hand-off and stash artifacts are kept for one day); the budget guard does not track that. |
| A web browser, `curl`, `tar`, `unzip`, `sha256sum` and `python3` | the [walkthrough](../examples/000/README.md) | Used to watch Jenkins and GitHub Actions and to check the artifacts. |
| Node.js 18+ (22+ for `hyperframes-walkthrough`), npm, ffmpeg and Chrome or Chromium | the video skills only (optional) | `nx setup` and `hfw setup` check these; see [skills.md](skills.md). Not needed to run the harness. |

Ports: the Jenkins controller listens on `127.0.0.1:18080` (change it with `J2GHA_JENKINS_PORT`).

## uv certificate errors

If `uv sync` or `uv run` fails while fetching packages (including the `hatchling` build dependency) with
`invalid peer certificate: UnknownIssuer`, try the system certificate store:

```sh
uv sync --system-certs
```

uv uses bundled Mozilla root certificates by default. A corporate proxy's CA may be trusted by your operating
system but absent from that bundle. To use system certificates for subsequent uv commands in the same shell:

```sh
export UV_SYSTEM_CERTS=true
uv sync
```

If the error persists, check that your organisation's approved CA is installed and trusted in your operating
system's certificate store, or use an approved PEM CA bundle via `SSL_CERT_FILE`. Do not disable certificate
verification with `--allow-insecure-host`. See [uv's TLS certificate documentation](https://docs.astral.sh/uv/concepts/authentication/certificates/).

## Jenkins image certificate errors

If `uv run j2gha docker build` fails at `jenkins-plugin-cli` with `SSLHandshakeException`,
`PKIX path building failed` or `unable to find valid certification path to requested target`, Java inside the
image cannot verify an HTTPS certificate. The plugin installer follows redirects from `updates.jenkins.io`
to `mirrors.updates.jenkins.io` and download mirrors; a corporate proxy may intercept only some of these hosts.
For example, a Zscaler-issued certificate on the mirror can cause this failure even when the initial update
center's certificate is trusted.

`UV_SYSTEM_CERTS=true` affects uv on the host only. Neither macOS Keychain trust nor Docker Desktop's registry
trust automatically installs a CA into the image's Linux certificate store or Java truststore.

Obtain your organisation's approved proxy CA certificate from IT or export the approved CA from your system's
certificate store in PEM format. Use a CA certificate, not the short-lived certificate served by the mirror,
and never include a private key. The existing `J2GHA_JENKINS_BASE` override lets you use a local CA-enabled base
without editing the repository's Dockerfile:

```sh
# Replace this path with your approved CA certificate (one PEM certificate).
ca_context="$(mktemp -d)"
cp /path/to/approved-proxy-ca.crt "$ca_context/proxy-ca.crt"
cat > "$ca_context/Dockerfile" <<'EOF'
FROM jenkins/jenkins:lts-jdk21@sha256:a660310e39ade10631f774bacd5219de767dfd08947ea5c32a739b5e5bb382c1
USER root
COPY proxy-ca.crt /usr/local/share/ca-certificates/j2gha-proxy-ca.crt
RUN update-ca-certificates \
 && keytool -importcert -noprompt -trustcacerts -cacerts \
      -storepass changeit -alias j2gha-proxy-ca \
      -file /usr/local/share/ca-certificates/j2gha-proxy-ca.crt
USER jenkins
EOF
docker build -t j2gha/jenkins-base:local-ca "$ca_context"
```

Then, from the repository root in the same shell:

```sh
export J2GHA_JENKINS_BASE=j2gha/jenkins-base:local-ca
uv run j2gha docker build --only jenkins
```

Keep the override set for later builds (including automatic builds by `jenkins up`). If the repository's pinned
Jenkins base changes, recreate the CA-enabled base from that new reference. The local image contains your
organisation's CA and is a custom build input; do not publish it without approval. After building, you can remove
the temporary context's two files and its empty directory.

This preserves TLS verification. Do not work around the failure by disabling verification or switching downloads
to HTTP. Other harness images have their own trust stores and may need separate CA configuration if their
downloads encounter the same proxy.

## Versions in use

Checked on 2026-10-11. These are the versions this repository was last run with, not minimums.

| Tool | Version |
|---|---|
| Docker Engine | 29.8.1 |
| uv | 0.11.21 |
| Python | 3.13.5 (unit tests also on 3.10.12) |
| GitHub CLI | 2.94.0 |
| git | 2.34.1 |
| Node.js, ffmpeg (video skills) | 22.17.0, 4.4.2 |

Pinned inside the harness, so they need no installation: Jenkins 2.580.1 (the LTS base image is pinned by digest in `docker/jenkins/Dockerfile`), act 0.2.89
(`docker/act/Dockerfile`), actionlint 1.7.12 and zizmor 1.30.1 (`j2gha/validate/static.py`).
