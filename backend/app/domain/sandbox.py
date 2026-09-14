"""Running code a candidate wrote, on the examination server.

This is the most dangerous thing the platform does. Everywhere else the server
decides what happens; here a candidate hands it a program and asks it to run.
The question is not whether someone will try to read the answer key, the
database password or another candidate's paper — it is what happens when they
do.

So the confinement is the feature and the execution is incidental:

* **No network.** The sandbox gets its own empty network namespace. A program
  cannot reach the database, the API, or the internet, so a leaked secret has
  nowhere to go and no second stage can be fetched.
* **Almost no filesystem.** Only the interpreter and the libraries it needs are
  bound in, read-only. ``/home``, ``/etc/shadow`` and the server's own ``.env``
  are not merely unreadable, they are absent. Work happens on a private tmpfs
  that dies with the process.
* **Its own pid, ipc and uts namespaces**, so one candidate's program cannot
  see or signal another's, or the server's.
* **No new privileges**, so a setuid binary inside the sandbox cannot elevate.
* **Hard resource limits** — address space, cpu time, file size, and a wall
  clock that kills the whole process group rather than the leader alone.

And one rule that matters more than any of the above: **if the sandbox is not
available, nothing runs.** There is no fallback to a bare subprocess. A grader
that quietly degrades to running candidate code unconfined is worse than one
that refuses, because the failure is invisible until it is not.

What this does not defend against, stated plainly so nobody assumes otherwise:

* A kernel bug that escapes a user namespace.
* Side channels between programs running at the same time.
* A fork bomb, by count. Processes are capped per *user* by the only limit
  available here, and the sandbox runs as the same user as the server — a cap
  low enough to matter would stop the server too. What bounds one is the wall
  clock and the memory ceiling, both of which apply, and the process-group
  kill that reaps whatever it spawned. Capping properly needs a cgroup, which
  needs privileges this deliberately does not take.
"""

from __future__ import annotations

import os
import resource
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

#: Read-only host paths the interpreter needs. Anything not listed is invisible
#: inside the sandbox — the allow-list is the point, so this is deliberately
#: short and deliberately not configurable from a request.
_RUNTIME_PATHS = ("/usr", "/bin", "/sbin", "/lib", "/lib64", "/etc/alternatives")

#: Beyond this, output is not evidence of anything except a loop with a print
#: in it. Truncating protects the grader's own memory.
MAX_OUTPUT_BYTES = 64 * 1024

DEFAULT_TIME_LIMIT_MS = 5_000
DEFAULT_MEMORY_LIMIT_MB = 256

#: Ceilings a question cannot exceed however it was authored. A mistyped limit
#: in the builder should not be able to hold a grading run open for an hour.
MAX_TIME_LIMIT_MS = 30_000
MAX_MEMORY_LIMIT_MB = 1_024


class Outcome(StrEnum):
    OK = "ok"
    #: Ran, exited non-zero. The candidate's program crashed.
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    #: Killed by the memory ceiling, or refused to start within it.
    OUT_OF_MEMORY = "out_of_memory"
    #: The sandbox itself could not run. Never a candidate's fault, and never
    #: scored as a wrong answer.
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class Execution:
    outcome: Outcome
    stdout: str
    stderr: str
    exit_code: int | None
    duration_ms: int

    @property
    def usable(self) -> bool:
        """Whether this result says anything about the candidate's program."""
        return self.outcome is not Outcome.UNAVAILABLE


class SandboxUnavailable(RuntimeError):
    """Raised when nothing can be run safely. Never caught to fall back."""


def _confinement_args(binary: str) -> list[str]:
    """The namespace and bind arguments every run shares.

    One list, used by both the real run and the availability probe, so the
    probe cannot pass under conditions the actual run would fail under — which
    is exactly what happened when it bound less than the interpreter needed.
    """
    argv = [binary, "--unshare-all", "--die-with-parent", "--new-session"]
    for path in _RUNTIME_PATHS:
        # Bound only if present, because these differ across distributions:
        # here /lib is a symlink into /usr, elsewhere it is a directory of its
        # own, and the dynamic loader has to be reachable either way.
        if os.path.exists(path):
            argv += ["--ro-bind", path, path]
    return argv


def sandbox_available() -> str | None:
    """The bubblewrap binary, or None if code cannot be run safely here.

    Checked by running something rather than by looking for the file:
    bubblewrap is present but useless on a kernel with unprivileged user
    namespaces disabled, which is a configuration a college machine can easily
    be in — and an availability check that says yes there is a check that
    reports the sandbox working when it is not.
    """
    binary = shutil.which("bwrap")
    if binary is None:
        return None
    try:
        probe = subprocess.run(
            _confinement_args(binary) + ["--proc", "/proc", "--tmpfs", "/tmp",
                                         "python3", "-I", "-c", "pass"],
            capture_output=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return binary if probe.returncode == 0 else None


def _limits(memory_mb: int) -> None:
    """Applied in the child, between fork and exec.

    Belt and braces alongside the namespace: the namespace decides what the
    program can *see*, these decide what it can *consume*. A fork bomb inside
    its own pid namespace still costs the host memory without them.
    """
    memory_bytes = memory_mb * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_OUTPUT_BYTES, MAX_OUTPUT_BYTES))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    # A second beyond the wall clock, so the timeout below is what normally
    # fires and the message a candidate sees is the accurate one.
    resource.setrlimit(resource.RLIMIT_CPU, (30, 31))
    # Deliberately NOT RLIMIT_NPROC. It is enforced per user id, and the
    # sandbox runs as the same user as the server, so a limit low enough to
    # stop a fork bomb is also low enough to stop bubblewrap starting at all —
    # the whole machine's processes for that user already exceed it. Capping
    # processes properly needs a cgroup, which needs delegation this does not
    # have. What bounds a fork bomb here is the wall clock and the memory
    # ceiling, and that is said plainly in the module docstring rather than
    # implied to be more.
    # Its own process group, so a timeout kills the children a program spawned
    # rather than only the program.
    os.setsid()


def run_python(
    source: str,
    stdin: str = "",
    *,
    time_limit_ms: int = DEFAULT_TIME_LIMIT_MS,
    memory_limit_mb: int = DEFAULT_MEMORY_LIMIT_MB,
) -> Execution:
    """Run one program against one input.

    Raises :class:`SandboxUnavailable` rather than running unconfined.
    """
    binary = sandbox_available()
    if binary is None:
        raise SandboxUnavailable(
            "bubblewrap is not usable on this machine, so candidate code cannot "
            "be run safely. Install bubblewrap and enable unprivileged user "
            "namespaces."
        )

    time_limit_ms = max(100, min(time_limit_ms, MAX_TIME_LIMIT_MS))
    memory_limit_mb = max(16, min(memory_limit_mb, MAX_MEMORY_LIMIT_MB))

    with tempfile.TemporaryDirectory(prefix="exam-run-") as work:
        program = Path(work) / "program.py"
        program.write_text(source)

        argv = _confinement_args(binary)
        argv += [
            "--proc", "/proc",
            "--dev", "/dev",
            # Writable, private, and gone when the process is. A program may
            # need scratch space; it must not keep any.
            "--tmpfs", "/tmp",
            "--ro-bind", str(program), "/program.py",
            "--chdir", "/tmp",
            "--setenv", "HOME", "/tmp",
            "--setenv", "PATH", "/usr/bin:/bin",
            # Unbuffered, or a program killed by the timeout appears to have
            # produced nothing at all.
            "--setenv", "PYTHONUNBUFFERED", "1",
            # Nothing the candidate writes to /tmp should ever be importable.
            "--setenv", "PYTHONDONTWRITEBYTECODE", "1",
            "--unsetenv", "PYTHONPATH",
            "python3", "-I", "/program.py",
        ]

        import time

        started = time.perf_counter()
        try:
            finished = subprocess.run(
                argv,
                input=stdin.encode()[:MAX_OUTPUT_BYTES],
                capture_output=True,
                timeout=time_limit_ms / 1000,
                preexec_fn=lambda: _limits(memory_limit_mb),  # noqa: PLW1509
            )
        except subprocess.TimeoutExpired as expired:
            return Execution(
                outcome=Outcome.TIMED_OUT,
                stdout=_text(expired.stdout),
                stderr="",
                exit_code=None,
                duration_ms=time_limit_ms,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return Execution(Outcome.UNAVAILABLE, "", str(exc), None, 0)

        duration_ms = int((time.perf_counter() - started) * 1000)
        stdout, stderr = _text(finished.stdout), _text(finished.stderr)

        if finished.returncode == 0:
            return Execution(Outcome.OK, stdout, stderr, 0, duration_ms)

        # MemoryError from the address-space limit, or the kernel's OOM killer.
        # Told apart from an ordinary crash because the two mean different
        # things to whoever reads the feedback.
        if "MemoryError" in stderr or finished.returncode == -9:
            return Execution(Outcome.OUT_OF_MEMORY, stdout, stderr, finished.returncode, duration_ms)

        return Execution(Outcome.FAILED, stdout, stderr, finished.returncode, duration_ms)


def _text(raw: bytes | None) -> str:
    """Bytes a candidate produced, made safe to store and show.

    Their program decides what comes out of it, so this assumes nothing:
    invalid UTF-8 is replaced rather than raising, and the length is capped.
    """
    if not raw:
        return ""
    text = raw[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")
    if len(raw) > MAX_OUTPUT_BYTES:
        text += "\n… output truncated"
    return text
