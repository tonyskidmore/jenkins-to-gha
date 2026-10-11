"""Disposable Jenkins controller (Docker + JCasC) and a small REST client for it."""

from __future__ import annotations

import base64
import fcntl
import html
import os
import re
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

import requests

from ..config import (DOCKER_DIR, JENKINS_BASE_IMAGE, JENKINS_CONTAINER, JENKINS_IMAGE, JENKINS_PASSWORD,
                      JENKINS_PORT, JENKINS_USER, STATE_DIR)

_held = 0  # re-entrant within one process


@contextmanager
def exclusive(purpose: str) -> Iterator[None]:
    """The controller is shared state (global env BRANCH_NAME/GIT_BRANCH, job names, fake credentials, tool
    installations): one harness process may use it at a time. Fails fast, naming the process holding it."""
    global _held
    if _held:
        _held += 1
        try:
            yield
        finally:
            _held -= 1
        return
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = STATE_DIR / "jenkins.lock"
    with open(path, "a+") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            f.seek(0)
            raise RuntimeError(f"the Jenkins controller is in use by another j2gha process ({f.read().strip() or '?'}); "
                               "wait for it to finish") from None
        f.seek(0)
        f.truncate()
        f.write(f"pid {os.getpid()}: {purpose}")
        f.flush()
        _held = 1
        try:
            yield
        finally:
            _held = 0
            f.seek(0)
            f.truncate()
            fcntl.flock(f, fcntl.LOCK_UN)


def _docker(*args: str, check: bool = True, capture: bool = True, timeout: int = 1800) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], check=check, capture_output=capture, text=True, timeout=timeout)


def build_image(quiet: bool = False) -> None:
    ctx = DOCKER_DIR / "jenkins"
    cmd = ["build", "-t", JENKINS_IMAGE, "--build-arg", f"JENKINS_BASE={JENKINS_BASE_IMAGE}", str(ctx)]
    if quiet:
        cmd.insert(1, "-q")
    print(f"[jenkins] building {JENKINS_IMAGE} from {ctx}", file=sys.stderr)
    _docker(*cmd, capture=False)


def container_running(name: str = JENKINS_CONTAINER) -> bool:
    out = _docker("ps", "-q", "-f", f"name=^{name}$", check=False)
    return bool(out.stdout.strip())


def up(docker_socket: bool = False, rebuild: bool = False, wait: bool = True) -> "Jenkins":
    """Start (or reuse) the controller container and wait until it answers."""
    if rebuild or _docker("image", "inspect", JENKINS_IMAGE, check=False).returncode != 0:
        build_image()
    if not container_running():
        _docker("rm", "-f", JENKINS_CONTAINER, check=False)
        args = ["run", "-d", "--name", JENKINS_CONTAINER, "-p", f"127.0.0.1:{JENKINS_PORT}:8080",
                "-e", f"J2GHA_ADMIN_PASSWORD={JENKINS_PASSWORD}", "--memory", "3g"]
        if docker_socket:
            # Lets `agent { docker }` / docker.image().inside work. This grants the controller control of
            # the host Docker daemon - only enable for pipelines you are prepared to run with that privilege.
            gid = _docker("run", "--rm", "-v", "/var/run/docker.sock:/var/run/docker.sock", "--entrypoint",
                          "stat", JENKINS_IMAGE, "-c", "%g", "/var/run/docker.sock", check=False).stdout.strip() or "0"
            args += ["-v", "/var/run/docker.sock:/var/run/docker.sock", "--group-add", gid,
                     "-e", "J2GHA_DOCKER=true"]
        args.append(JENKINS_IMAGE)
        _docker(*args)
        print(f"[jenkins] started {JENKINS_CONTAINER} on http://127.0.0.1:{JENKINS_PORT}", file=sys.stderr)
    j = Jenkins()
    if wait:
        j.wait_ready()
    return j


def down() -> None:
    _docker("rm", "-f", JENKINS_CONTAINER, check=False)


def docker_enabled() -> bool:
    out = _docker("inspect", "-f", "{{range .Mounts}}{{.Source}} {{end}}", JENKINS_CONTAINER, check=False)
    return "docker.sock" in out.stdout


@dataclass
class BuildResult:
    job: str
    number: int
    result: str | None
    duration_ms: int
    console: str
    stages: list[dict[str, Any]]
    url: str
    approved_inputs: list[str] | None = None  # stage of every input auto-approved (None: inputs were not approved)


class Jenkins:
    def __init__(self, base: str | None = None, user: str = JENKINS_USER, password: str = JENKINS_PASSWORD):
        self.base = (base or f"http://127.0.0.1:{JENKINS_PORT}").rstrip("/")
        self.s = requests.Session()
        self.s.auth = (user, password)
        self._crumb: dict[str, str] | None = None

    # ------------------------------------------------------------ basics
    def wait_ready(self, timeout: int = 240) -> None:
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            try:
                r = self.s.get(f"{self.base}/api/json", timeout=5)
                if r.status_code == 200:
                    return
                last = r.status_code
            except requests.RequestException as e:  # noqa: PERF203
                last = type(e).__name__
            time.sleep(2)
        raise RuntimeError(f"Jenkins not ready after {timeout}s (last: {last}); see `docker logs {JENKINS_CONTAINER}`")

    def available(self) -> bool:
        try:
            return self.s.get(f"{self.base}/api/json", timeout=3).status_code == 200
        except requests.RequestException:
            return False

    def crumb(self) -> dict[str, str]:
        if self._crumb is None:
            r = self.s.get(f"{self.base}/crumbIssuer/api/json", timeout=10)
            r.raise_for_status()
            d = r.json()
            self._crumb = {d["crumbRequestField"]: d["crumb"]}
        return self._crumb

    def post(self, path: str, **kw: Any) -> requests.Response:
        headers = {**self.crumb(), **kw.pop("headers", {})}
        return self.s.post(f"{self.base}{path}", headers=headers, timeout=kw.pop("timeout", 60), **kw)

    # ------------------------------------------------- declarative model
    def to_json(self, jenkinsfile: str) -> dict:
        """Jenkins' own Declarative AST (pipeline-model-definition). No crumb needed for these endpoints."""
        r = self.s.post(f"{self.base}/pipeline-model-converter/toJson", data={"jenkinsfile": jenkinsfile}, timeout=60)
        r.raise_for_status()
        return r.json().get("data", {})

    def validate(self, jenkinsfile: str) -> tuple[bool, str]:
        r = self.s.post(f"{self.base}/pipeline-model-converter/validate", data={"jenkinsfile": jenkinsfile}, timeout=60)
        r.raise_for_status()
        text = r.text.strip()
        return text.startswith("Jenkinsfile successfully validated"), text

    def script(self, groovy: str) -> str:
        """Run Groovy in the script console (admin only; local disposable controller)."""
        r = self.post("/scriptText", data={"script": groovy})
        r.raise_for_status()
        return r.text

    def approve_script(self, script: str) -> None:
        """Pre-approve a non-sandboxed pipeline script (only sensible on this disposable controller)."""
        b64 = base64.b64encode(script.encode("utf-8")).decode()
        out = self.script(
            "import org.jenkinsci.plugins.scriptsecurity.scripts.ScriptApproval\n"
            "import org.jenkinsci.plugins.scriptsecurity.scripts.languages.GroovyLanguage\n"
            f"ScriptApproval.get().preapprove(new String('{b64}'.decodeBase64(), 'UTF-8'), GroovyLanguage.get())\n"
            "println 'approved'"
        )
        if "approved" not in out:
            raise RuntimeError(f"script approval failed: {out[:500]}")

    def set_global_env(self, values: dict[str, str]) -> None:
        """Set controller-wide environment variables (e.g. BRANCH_NAME for `when { branch }`)."""
        lines = ["import hudson.slaves.EnvironmentVariablesNodeProperty", "def j = jenkins.model.Jenkins.get()",
                 "def props = j.globalNodeProperties.getAll(EnvironmentVariablesNodeProperty)",
                 "def p = props ? props[0] : null",
                 "if (p == null) { p = new EnvironmentVariablesNodeProperty(); j.globalNodeProperties.add(p) }",
                 "def env = p.envVars"]
        for k, v in values.items():
            kb = base64.b64encode(k.encode()).decode()
            vb = base64.b64encode(str(v).encode()).decode()
            lines.append(f"env.put(new String('{kb}'.decodeBase64(), 'UTF-8'), new String('{vb}'.decodeBase64(), 'UTF-8'))")
        lines += ["j.save()", "println 'ok'"]
        out = self.script("\n".join(lines))
        if "ok" not in out:
            raise RuntimeError(f"set_global_env failed: {out[:500]}")

    # ------------------------------------------------------------- jobs
    def upsert_pipeline_job(self, name: str, script: str, sandbox: bool = False, description: str = "",
                            parameters: list[dict[str, Any]] | None = None) -> None:
        """``parameters`` define the job's build parameters up front (see `parameter_definitions_xml`), so the first
        build can already receive them; without them a Declarative pipeline registers its parameters by running."""
        props = parameter_definitions_xml(parameters) if parameters else "<properties/>"
        xml = (
            "<?xml version='1.1' encoding='UTF-8'?>\n"
            "<flow-definition plugin=\"workflow-job\">"
            f"<description>{html.escape(description)}</description>"
            f"<keepDependencies>false</keepDependencies>{props}"
            "<definition class=\"org.jenkinsci.plugins.workflow.cps.CpsFlowDefinition\" plugin=\"workflow-cps\">"
            f"<script>{html.escape(script)}</script><sandbox>{str(sandbox).lower()}</sandbox>"
            "</definition><triggers/><disabled>false</disabled></flow-definition>"
        )
        headers = {"Content-Type": "application/xml; charset=utf-8"}
        exists = self.s.get(f"{self.base}/job/{name}/api/json", timeout=10).status_code == 200
        # Jenkins' parsing of the posted XML can duplicate a fragment of the script when an entity reference meets a
        # parser buffer boundary (deterministic in the byte layout: example 121's localised script, 27 characters
        # repeated at offset 22000), after which the stored script is not the approved one ("script not yet approved
        # for use"). Read the stored script back and, when it differs, post again with the layout shifted.
        for nudge in range(4):
            body = xml.replace("</description>", " " * nudge + "</description>", 1).encode("ascii", "xmlcharrefreplace")
            if exists:
                r = self.post(f"/job/{name}/config.xml", data=body, headers=headers)
            else:
                r = self.post(f"/createItem?name={name}", data=body, headers=headers)
                exists = r.status_code < 400
            if r.status_code >= 400:
                raise RuntimeError(f"create/update job {name} failed: {r.status_code} {r.text[:500]}")
            stored = self.job_script(name)
            if stored == script:
                break
            print(f"[jenkins] {name}: stored script differs from the posted one ({len(stored)} vs {len(script)} "
                  f"chars); posting again with the layout shifted", file=sys.stderr)
        else:
            raise RuntimeError(f"job {name}: the controller keeps storing a script that differs from the posted one")
        if not sandbox:
            self.approve_script(script)

    def job_script(self, name: str) -> str:
        """The pipeline script the controller holds for a job, read back from its config.xml."""
        r = self.s.get(f"{self.base}/job/{name}/config.xml", timeout=30)
        r.raise_for_status()
        m = re.search(r"<script>(.*?)</script>", r.content.decode("utf-8"), re.S)
        return html.unescape(m.group(1)) if m else ""

    def delete_job(self, name: str) -> None:
        self.post(f"/job/{name}/doDelete")

    def trigger(self, name: str, params: dict[str, Any] | None = None) -> int:
        attempts = ([("buildWithParameters", params)] if params else []) + [("build", None),
                                                                           ("buildWithParameters", None)]
        r = None
        for endpoint, data in attempts:  # parameterised jobs reject /build; new jobs reject buildWithParameters
            r = self.post(f"/job/{name}/{endpoint}", data=data)
            if r.status_code in (200, 201):
                break
        if r.status_code not in (200, 201):
            raise RuntimeError(f"trigger {name} failed: {r.status_code} {r.text[:300]}")
        queue_url = r.headers.get("Location", "").rstrip("/")
        deadline = time.time() + 120
        while time.time() < deadline:
            q = self.s.get(f"{queue_url}/api/json", timeout=10).json()
            exe = q.get("executable")
            if exe and exe.get("number"):
                return int(exe["number"])
            if q.get("cancelled"):
                raise RuntimeError(f"queue item for {name} was cancelled")
            time.sleep(1)
        raise RuntimeError(f"build for {name} did not leave the queue: {q.get('why')}")

    def build_info(self, name: str, number: int) -> dict:
        return self.s.get(f"{self.base}/job/{name}/{number}/api/json", timeout=20).json()

    def build_outputs(self, name: str, number: int, cap: int | None = None) -> dict[str, Any]:
        """Archived files (path, size, sha256) and test cases of a build, for the full-mode output comparison.
        `tests` is None when the build recorded no test report. A file that cannot be read whole within the download
        cap keeps no hash and is recorded as a problem (the comparison is then incomplete, see outputs.compare_outputs)."""
        from urllib.parse import quote

        from ..outputs import DOWNLOAD_CAP, file_entry, jenkins_cases
        cap = DOWNLOAD_CAP if cap is None else cap
        build = f"{self.base}/job/{name}/{number}"
        info = self.s.get(f"{build}/api/json", params={"tree": "artifacts[relativePath]"}, timeout=30).json()
        archived, problems, room = [], [], cap
        for a in info.get("artifacts") or []:
            path = a["relativePath"]
            r = self.s.get(f"{build}/artifact/{quote(path)}", timeout=120, stream=True)
            if r.status_code != 200:
                problems.append(f"Jenkins artifact {path}: HTTP {r.status_code}")
                archived.append(file_entry(path, None))
                continue
            data = _read_capped(r, room)  # the cap holds while streaming, whatever Content-Length says
            if data is None:
                problems.append(f"Jenkins artifact {path}: over the download cap ({cap} bytes per build)")
                archived.append(file_entry(path, None))
                continue
            room -= len(data)
            archived.append(file_entry(path, data))
        r = self.s.get(f"{build}/testReport/api/json",
                       params={"tree": "suites[cases[className,name,status]]"}, timeout=60)
        tests = jenkins_cases(r.json()) if r.status_code == 200 else None
        if r.status_code not in (200, 404):  # 404: the build recorded no test report
            problems.append(f"Jenkins test report: HTTP {r.status_code}")
        out: dict[str, Any] = {"archived": archived, "tests": tests}
        if problems:
            out["problems"] = problems
        return out

    def pending_inputs(self, name: str, number: int) -> list[dict]:
        r = self.s.get(f"{self.base}/job/{name}/{number}/wfapi/pendingInputActions", timeout=10)
        return r.json() if r.status_code == 200 else []

    def approve_input(self, name: str, number: int, input_id: str) -> None:
        self.post(f"/job/{name}/{number}/input/{input_id}/proceedEmpty")

    def wait(self, name: str, number: int, timeout: int = 1800, auto_approve_inputs: bool = True) -> BuildResult:
        deadline = time.time() + timeout
        info = {}
        approved: list[str] = []
        while time.time() < deadline:
            info = self.build_info(name, number)
            if not info.get("building"):
                break
            if auto_approve_inputs:
                pending = self.pending_inputs(name, number)
                if pending:  # which stage asked: the converted run must enter that stage's environment
                    approved += self.paused_stages(name, number) or ["(unknown stage)"] * len(pending)
                for p in pending:
                    self.approve_input(name, number, p.get("id"))
            time.sleep(2)
        else:
            self.post(f"/job/{name}/{number}/stop")
            info = self.build_info(name, number)
            info.setdefault("result", "TIMEOUT")
        console = self.s.get(f"{self.base}/job/{name}/{number}/consoleText", timeout=60).text
        stages = []
        r = self.s.get(f"{self.base}/job/{name}/{number}/wfapi/describe", timeout=30)
        if r.status_code == 200:
            stages = [{"name": s.get("name"), "status": s.get("status"), "durationMillis": s.get("durationMillis")}
                      for s in r.json().get("stages", [])]
        return BuildResult(job=name, number=number, result=info.get("result"), duration_ms=info.get("duration", 0),
                           console=console, stages=stages, url=f"{self.base}/job/{name}/{number}/",
                           approved_inputs=approved if auto_approve_inputs else None)

    def paused_stages(self, name: str, number: int) -> list[str]:
        """Stages waiting for an input (wfapi status PAUSED_PENDING_INPUT)."""
        r = self.s.get(f"{self.base}/job/{name}/{number}/wfapi/describe", timeout=30)
        return [s.get("name") for s in (r.json().get("stages") or [])
                if s.get("status") == "PAUSED_PENDING_INPUT"] if r.status_code == 200 else []


def _read_capped(r: Any, room: int) -> bytes | None:
    """The response body, or None as soon as it exceeds `room` bytes (the response is closed)."""
    if int(r.headers.get("Content-Length") or 0) > room:
        r.close()
        return None
    buf = bytearray()
    for chunk in r.iter_content(chunk_size=1 << 16):
        buf += chunk
        if len(buf) > room:
            r.close()
            return None
    return bytes(buf)


def parameter_definitions_xml(parameters: list[dict[str, Any]]) -> str:
    """`<properties>` with a ParametersDefinitionProperty. Each parameter is {name, kind, default, choices} with kind
    string | booleanParam | choice | text | password; the caller only passes parameters it can define faithfully."""
    esc = html.escape
    out = []
    for p in parameters:
        name, kind, default = esc(str(p["name"])), p["kind"], p.get("default")
        if kind == "booleanParam":
            out.append(f"<hudson.model.BooleanParameterDefinition><name>{name}</name>"
                       f"<defaultValue>{str(bool(default)).lower()}</defaultValue></hudson.model.BooleanParameterDefinition>")
        elif kind == "choice":
            items = "".join(f"<string>{esc(str(c))}</string>" for c in p["choices"])
            out.append(f"<hudson.model.ChoiceParameterDefinition><name>{name}</name><choices class=\"java.util.Arrays$ArrayList\">"
                       f"<a class=\"string-array\">{items}</a></choices></hudson.model.ChoiceParameterDefinition>")
        elif kind in ("text", "string"):
            cls = "TextParameterDefinition" if kind == "text" else "StringParameterDefinition"
            out.append(f"<hudson.model.{cls}><name>{name}</name><defaultValue>{esc(str(default if default is not None else ''))}"
                       f"</defaultValue></hudson.model.{cls}>")
        elif kind == "password":
            out.append(f"<hudson.model.PasswordParameterDefinition><name>{name}</name>"
                       f"<defaultValue>{esc(str(default or ''))}</defaultValue></hudson.model.PasswordParameterDefinition>")
        else:
            raise ValueError(f"cannot define a {kind!r} parameter in the job XML")
    return ("<properties><hudson.model.ParametersDefinitionProperty><parameterDefinitions>" + "".join(out) +
            "</parameterDefinitions></hudson.model.ParametersDefinitionProperty></properties>")
