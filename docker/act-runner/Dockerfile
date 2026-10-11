# j2gha act job-container image: catthehacker's ubuntu-latest lookalike (what act maps `runs-on: ubuntu-*` to,
# see j2gha/runners/act.py) plus the toolchain the Jenkins image (docker/jenkins/Dockerfile) gives real-world `sh`
# steps, so a full-mode run finds the same Maven, Python/YAML and Xvfb on both sides. The base already ships git,
# make, gcc, python3 and Node (act toolcache).
# Reproducible inputs: the base image is pinned by digest (the tag is only for readability). Ubuntu packages
# (apt-get below) are not pinned.
ARG ACT_RUNNER_BASE=catthehacker/ubuntu:act-latest@sha256:c58e2b364da03b0c804c7d660f2ecbedf2f221a382b9baa0b344b0144780ff43
FROM ${ACT_RUNNER_BASE}

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      openjdk-21-jdk-headless python3-yaml python-is-python3 xvfb libgtk-3-0t64 zip \
 && rm -rf /var/lib/apt/lists/*

# Maven 3.9.16 from apache.org (the apt maven on Ubuntu 24.04 is 3.8.7; Tycho 4 and other current builds need 3.9,
# which the Jenkins image has from Debian 13). Pinned by version and sha512; change both together.
ARG MAVEN_VERSION=3.9.16
ARG MAVEN_SHA512=831a8591fe20c8243b1dbe7d71e3244f31d1665b0804b2e825e38cbbe5ce0cafb8338851f90780735568773e0a6cd07bbec107cda0b896b008b861075358b6f6
RUN curl -fsSL -o /tmp/maven.tar.gz "https://dlcdn.apache.org/maven/maven-3/${MAVEN_VERSION}/binaries/apache-maven-${MAVEN_VERSION}-bin.tar.gz" \
 && echo "${MAVEN_SHA512}  /tmp/maven.tar.gz" | sha512sum -c - \
 && mkdir -p /opt/maven && tar -xzf /tmp/maven.tar.gz -C /opt/maven --strip-components=1 && rm /tmp/maven.tar.gz \
 && ln -sf /opt/maven/bin/mvn /usr/local/bin/mvn && mvn -v

# Provenance, read by j2gha.runners.images.image_provenance() without starting a container.
ARG ACT_RUNNER_BASE
LABEL j2gha.base-image="${ACT_RUNNER_BASE}"
