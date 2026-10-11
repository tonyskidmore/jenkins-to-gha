# act (nektos/act) packaged with the docker CLI so the harness can run it without a host install.
# act talks to the host Docker daemon through the mounted socket and starts sibling job containers.
# Reproducible inputs: the base image is pinned by digest (the tag is only for readability) and the act release
# tarball by sha256 (from the release's checksums.txt; change ACT_VERSION and ACT_SHA256 together).
# Alpine packages (apk add below) are not pinned.
ARG DOCKER_CLI_BASE=docker:29-cli@sha256:b1805116a6a86cc591b5d5f60a910a0715cdcc9d18d866ad68b1457ead25c35c
FROM ${DOCKER_CLI_BASE}
ARG DOCKER_CLI_BASE
ARG ACT_VERSION=0.2.89
ARG ACT_SHA256=0191d6f1f3b716b5c55820032605d05fc3c1cdbf581ebeff655019e5dd1524c0
RUN apk add --no-cache git bash curl ca-certificates \
 && curl -fsSL -o /tmp/act.tar.gz "https://github.com/nektos/act/releases/download/v${ACT_VERSION}/act_Linux_x86_64.tar.gz" \
 && echo "${ACT_SHA256}  /tmp/act.tar.gz" | sha256sum -c - \
 && tar -xzf /tmp/act.tar.gz -C /usr/local/bin act \
 && rm /tmp/act.tar.gz \
 && act --version
# Provenance, read by j2gha.runners.images.image_provenance() without starting a container.
LABEL j2gha.act-version="${ACT_VERSION}" j2gha.base-image="${DOCKER_CLI_BASE}"
ENTRYPOINT ["act"]
