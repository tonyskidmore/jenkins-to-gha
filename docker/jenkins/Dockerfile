# j2gha Jenkins image: a disposable, JCasC-configured controller used for
#   1. authoritative Declarative AST extraction (/pipeline-model-converter/toJson + validate)
#   2. Groovy AST dumping with Jenkins' own bundled Groovy (offline, no controller start)
#   3. executing (localised) Jenkinsfiles on the built-in node
#
# Reproducible inputs: the base image is pinned by digest (the tag is only for readability) and plugins.txt pins every
# plugin, dependencies included. j2gha passes JENKINS_BASE from j2gha/config.py (JENKINS_BASE_IMAGE, env
# J2GHA_JENKINS_BASE), so change the digest there too. Debian packages (apt-get below) are not pinned.
ARG JENKINS_BASE=jenkins/jenkins:lts-jdk21@sha256:a660310e39ade10631f774bacd5219de767dfd08947ea5c32a739b5e5bb382c1
FROM ${JENKINS_BASE}

USER root
# Tooling the built-in executor needs to run typical real-world `sh` steps. The harness runner images
# (docker/runner, docker/act-runner) install the same toolchain, so full-mode runs see it on both sides.
#   - docker-cli: Debian's docker.io ships no /usr/bin/docker client (that is the separate docker-cli package), and
#     `jenkins up --docker` runs need it for `sh 'docker build ...'`.
#   - tigervnc-standalone-server, xauth, xvfb, libgtk-3-0t64: Xvnc-wrapped SWT/Tycho builds (xvnc plugin).
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      git curl unzip zip jq make python3 python3-venv python3-pip python3-yaml python-is-python3 \
      maven nodejs npm ca-certificates docker.io docker-cli \
      tigervnc-standalone-server xauth xvfb libgtk-3-0t64 \
 && rm -rf /var/lib/apt/lists/*

# Extract the exact Groovy runtime bundled in jenkins.war for offline AST dumps.
RUN mkdir -p /opt/j2gha \
 && cd /tmp && unzip -q -o /usr/share/jenkins/jenkins.war 'WEB-INF/lib/groovy-all-*.jar' \
 && cp WEB-INF/lib/groovy-all-*.jar /opt/j2gha/groovy-all.jar && rm -rf WEB-INF
COPY groovy/ /opt/j2gha/
COPY bin/j2gha-ast bin/j2gha-check-plugins /usr/local/bin/
RUN chmod +x /usr/local/bin/j2gha-ast /usr/local/bin/j2gha-check-plugins

COPY certs/KAINOS-ZSCALER-G2.cer /tmp/company-ca.cer
RUN keytool -importcert -noprompt -trustcacerts \
      -alias company-ca \
      -file /tmp/company-ca.cer \
      -keystore "$JAVA_HOME/lib/security/cacerts" \
      -storepass changeit \
 && rm /tmp/company-ca.cer

USER jenkins
# Adding or upgrading a plugin: put its bare name (or name:version) in plugins.txt and rebuild. The pin check then
# fails and prints the resolved `name:version` lines for it and any new dependencies (`+`); copy those into
# plugins.txt and rebuild. A different JENKINS_BASE may need different plugin versions (jenkins-plugin-cli says so).
COPY plugins.txt /usr/share/jenkins/ref/plugins.txt
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN jenkins-plugin-cli --plugin-file /usr/share/jenkins/ref/plugins.txt --verbose 2>&1 | tail -5 \
 && j2gha-check-plugins

COPY casc/ /var/jenkins_casc/
ENV CASC_JENKINS_CONFIG=/var/jenkins_casc \
    JAVA_OPTS="-Djenkins.install.runSetupWizard=false -Dhudson.plugins.git.GitSCM.ALLOW_LOCAL_CHECKOUT=true -Dorg.jenkinsci.plugins.durabletask.BourneShellScript.HEARTBEAT_CHECK_INTERVAL=86400 -Xmx1g"

# Provenance: the pinned base reference (the Jenkins core version is the inherited org.opencontainers.image.version).
ARG JENKINS_BASE
LABEL j2gha.base-image="${JENKINS_BASE}"
