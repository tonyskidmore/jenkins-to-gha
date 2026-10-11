# Security

This is a prototype, not a production service. It runs third-party build scripts in local containers and a local
Jenkins with pre-approved scripts; read the [security posture](docs/architecture.md#security-posture) before running it,
and never expose the Jenkins controller. Your own GitHub login (`gh auth`) is what the harness uses to search GitHub
and to start runs in your repository; never give production credentials to the Jenkins controller or to the pipelines
it tests, which run with fake credentials by design.

## Reporting a vulnerability

Please report it privately through GitHub's private vulnerability reporting: the repository's **Security** tab, then
**Report a vulnerability**. Do not open a public issue. Only the latest commit on the default branch is looked at.
