# j2gha JIT self-hosted runner image: the upstream GitHub Actions runner plus the toolchain the Jenkins image
# (docker/jenkins/Dockerfile) gives real-world `sh` steps, so a full-mode run finds the same Maven, Node, make,
# Python and Xvfb on both sides and a difference is a conversion difference, not a missing tool.
# The harness starts it with `./run.sh --jitconfig ...` (j2gha/gha/remote.py), so ENTRYPOINT/CMD/WORKDIR and the
# `runner` user are inherited unchanged.
# Reproducible inputs: the base image is pinned by digest (the tag is only for readability). Ubuntu packages
# (apt-get below) are not pinned; Node is pinned below.
ARG RUNNER_BASE=ghcr.io/actions/actions-runner:latest@sha256:4ffadc0002b2581327e06101fc8c06cd189232baf79fe561fac9caeb76f5e807
FROM ${RUNNER_BASE}

USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      git curl unzip zip jq make python3 python3-venv python3-pip python3-yaml python-is-python3 \
      openjdk-21-jdk-headless ca-certificates xz-utils xvfb libgtk-3-0t64 \
 && rm -rf /var/lib/apt/lists/*
# Node 20 from nodejs.org (Ubuntu 24.04's apt nodejs is 18, below the `engines` of current npm projects; the Jenkins
# image has Debian 13's Node 20). Pinned by version and sha256; change NODE_VERSION and NODE_SHA256 together.
ARG NODE_VERSION=20.20.2
ARG NODE_SHA256=df770b2a6f130ed8627c9782c988fda9669fa23898329a61a871e32f965e007d
RUN curl -fsSL -o /tmp/node.tar.xz "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz" \
 && echo "${NODE_SHA256}  /tmp/node.tar.xz" | sha256sum -c - \
 && tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1 --exclude='*/CHANGELOG.md' --exclude='*/README.md' \
 && rm /tmp/node.tar.xz && node --version && npm --version
# Maven 3.9.16 from apache.org (the apt maven on Ubuntu 24.04 is 3.8.7; Tycho 4 and other current builds need 3.9, which the
# Jenkins image has from Debian 13). Pinned by version and sha512; change MAVEN_VERSION and MAVEN_SHA512 together.
ARG MAVEN_VERSION=3.9.16
ARG MAVEN_SHA512=831a8591fe20c8243b1dbe7d71e3244f31d1665b0804b2e825e38cbbe5ce0cafb8338851f90780735568773e0a6cd07bbec107cda0b896b008b861075358b6f6
RUN curl -fsSL -o /tmp/maven.tar.gz "https://dlcdn.apache.org/maven/maven-3/${MAVEN_VERSION}/binaries/apache-maven-${MAVEN_VERSION}-bin.tar.gz" \
 && echo "${MAVEN_SHA512}  /tmp/maven.tar.gz" | sha512sum -c - \
 && mkdir -p /opt/maven && tar -xzf /tmp/maven.tar.gz -C /opt/maven --strip-components=1 && rm /tmp/maven.tar.gz \
 && ln -sf /opt/maven/bin/mvn /usr/local/bin/mvn && mvn -v
USER runner

# Provenance, read by j2gha.runners.images.image_provenance() without starting a container.
ARG RUNNER_BASE
LABEL j2gha.base-image="${RUNNER_BASE}"
