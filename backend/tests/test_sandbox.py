"""Confinement, not execution.

That a program runs is the easy half and barely worth a test. These assert the
half that matters: a candidate's program cannot reach the network, cannot read
the server's secrets, cannot outlive its limits, and cannot be run at all when
the sandbox is missing.

Each of these is a thing someone will actually try during an examination.
"""

import textwrap

import pytest

from app.domain.sandbox import (
    MAX_OUTPUT_BYTES,
    Outcome,
    SandboxUnavailable,
    run_python,
    sandbox_available,
)

pytestmark = pytest.mark.skipif(
    sandbox_available() is None,
    reason="needs bubblewrap and unprivileged user namespaces",
)


def run(source: str, **kwargs):
    return run_python(textwrap.dedent(source), **kwargs)


class TestItRuns:
    def test_a_program_produces_its_output(self):
        result = run("print('hello')")
        assert result.outcome is Outcome.OK
        assert result.stdout.strip() == "hello"

    def test_a_program_reads_its_input(self):
        result = run("print(sum(int(n) for n in input().split()))", stdin="1 2 3\n")
        assert result.stdout.strip() == "6"

    def test_a_crash_is_reported_rather_than_raised(self):
        """A candidate's bug is a result, not an error in the grader."""
        result = run("raise ValueError('boom')")
        assert result.outcome is Outcome.FAILED
        assert "ValueError" in result.stderr
        assert result.exit_code != 0


class TestTheNetworkIsGone:
    def test_a_program_cannot_open_a_connection(self):
        # The first thing to try with code execution on someone else's server.
        result = run(
            """
            import socket
            try:
                socket.create_connection(('1.1.1.1', 80), timeout=3)
                print('REACHED')
            except OSError as exc:
                print('blocked', type(exc).__name__)
            """
        )
        assert "REACHED" not in result.stdout
        assert "blocked" in result.stdout

    def test_a_program_cannot_reach_the_database(self):
        """Where every candidate's answers and the whole answer key live."""
        result = run(
            """
            import socket
            for port in (5432, 5435, 6379, 6380, 8000, 8010):
                try:
                    socket.create_connection(('127.0.0.1', port), timeout=1)
                    print('REACHED', port)
                except OSError:
                    pass
            print('done')
            """
        )
        assert "REACHED" not in result.stdout
        assert "done" in result.stdout


class TestTheFilesystemIsGone:
    def test_the_servers_own_configuration_is_invisible(self):
        """backend/.env holds the JWT signing secret and the database password.
        Reading it would let someone mint a token for any account."""
        result = run(
            """
            import glob, os
            for pattern in ('/home/*/testseries/backend/.env', '/etc/shadow', '/root/*'):
                if glob.glob(pattern):
                    print('FOUND', pattern)
            print(os.path.exists('/home'), os.path.exists('/root'))
            """
        )
        assert "FOUND" not in result.stdout
        assert result.stdout.strip().endswith("False False")

    def test_the_source_of_the_application_is_invisible(self):
        result = run(
            """
            import os
            print(os.path.exists('/home/rakshuu/testseries/backend/app/core/security.py'))
            """
        )
        assert result.stdout.strip() == "False"

    def test_writes_go_to_a_private_tmpfs_that_does_not_persist(self):
        first = run("open('/tmp/left-behind', 'w').write('x'); print('wrote')")
        assert first.outcome is Outcome.OK
        second = run("import os; print(os.path.exists('/tmp/left-behind'))")
        assert second.stdout.strip() == "False"

    def test_the_runtime_is_read_only(self):
        result = run(
            """
            try:
                open('/usr/lib/python3.12/os.py', 'a').write('# tampered')
                print('WROTE')
            except OSError as exc:
                print('read only', type(exc).__name__)
            """
        )
        assert "WROTE" not in result.stdout


class TestLimits:
    def test_an_endless_loop_is_stopped(self):
        result = run("while True: pass", time_limit_ms=1_000)
        assert result.outcome is Outcome.TIMED_OUT

    def test_sleeping_counts_against_the_clock_too(self):
        """Wall clock, not CPU time: a program that sleeps for an hour is as
        stuck as one that spins, and the candidate is waiting either way."""
        result = run("import time; time.sleep(30)", time_limit_ms=1_000)
        assert result.outcome is Outcome.TIMED_OUT

    def test_a_program_cannot_take_more_memory_than_it_is_given(self):
        result = run("x = bytearray(512 * 1024 * 1024); print(len(x))", memory_limit_mb=64)
        assert result.outcome in (Outcome.OUT_OF_MEMORY, Outcome.FAILED)
        assert "536870912" not in result.stdout

    def test_endless_output_is_truncated_rather_than_filling_the_grader(self):
        result = run(
            """
            import sys
            for _ in range(200000):
                sys.stdout.write('x' * 100)
            """,
            time_limit_ms=4_000,
        )
        assert len(result.stdout) <= MAX_OUTPUT_BYTES + 64

    def test_a_child_process_does_not_outlive_the_timeout(self):
        """Killing only the leader leaves whatever it spawned running on the
        examination server after the grader has moved on."""
        result = run(
            """
            import subprocess, sys, time
            subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
            time.sleep(60)
            """,
            time_limit_ms=1_500,
        )
        assert result.outcome is Outcome.TIMED_OUT


class TestOutputHandling:
    def test_bytes_that_are_not_text_do_not_break_the_grader(self):
        """The candidate chooses what comes out; it need not be valid UTF-8."""
        result = run("import sys; sys.stdout.buffer.write(b'\\xff\\xfe ok')")
        assert "ok" in result.stdout


class TestRefusingToRunUnsafely:
    def test_it_raises_rather_than_running_unconfined(self, monkeypatch):
        """The rule the whole module rests on. A grader that silently falls
        back to a bare subprocess is worse than one that stops, because
        nobody finds out until afterwards."""
        monkeypatch.setattr("app.domain.sandbox.sandbox_available", lambda: None)
        with pytest.raises(SandboxUnavailable):
            run_python("print('should never run')")


class TestAForkBomb:
    def test_one_is_stopped_by_the_clock_even_though_it_is_not_capped(self):
        """Honest about which defence is doing the work.

        There is no process-count limit — RLIMIT_NPROC is per user id, and the
        sandbox shares the server's, so a useful cap would stop the server.
        What contains a bomb is the wall clock and the process-group kill, so
        that is what this asserts.
        """
        result = run(
            """
            import os, time
            for _ in range(60):
                if os.fork() == 0:
                    time.sleep(30)
                    os._exit(0)
            time.sleep(30)
            """,
            time_limit_ms=1_500,
            memory_limit_mb=64,
        )
        assert result.outcome in (Outcome.TIMED_OUT, Outcome.FAILED, Outcome.OUT_OF_MEMORY)

    def test_an_ordinary_subprocess_still_works(self):
        """A candidate may reasonably use a helper process, and nothing here
        should break that."""
        result = run(
            """
            import subprocess, sys
            out = subprocess.run([sys.executable, '-c', 'print(6*7)'], capture_output=True)
            print(out.stdout.decode().strip())
            """,
            time_limit_ms=8_000,
        )
        assert result.outcome is Outcome.OK
        assert result.stdout.strip() == "42"
