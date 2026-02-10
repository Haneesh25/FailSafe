"""Tests for the Failsafe CLI."""

import sys, os, io, tempfile, subprocess
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_cli_help():
    r = subprocess.run([sys.executable, "-m", "agentpact.cli", "--help"],
                       capture_output=True, text=True, timeout=10)
    assert r.returncode == 0
    assert "watch" in r.stdout
    assert "demo" in r.stdout
    assert "report" in r.stdout


def test_watch_mode_script():
    script = '''
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agentpact import Failsafe

fs = Failsafe()
fs.agent("a", authority="read_only")
fs.agent("b", authority="read_only")
fs.contract("a", "b", fields={"test": "string"})
fs.validate("a", "b", {"test": "hello"})
'''
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(script)
        path = f.name
    try:
        r = subprocess.run(
            [sys.executable, "-m", "agentpact.cli", "watch", path],
            capture_output=True, text=True, timeout=10,
            cwd=os.path.dirname(os.path.abspath(__file__)),
        )
        assert "watching handoffs" in r.stdout.lower()
        assert "a" in r.stdout and "b" in r.stdout
    finally:
        os.unlink(path)


def test_ansi_formatting():
    from agentpact import Failsafe
    from agentpact.cli import print_validation

    fs = Failsafe()
    fs.agent("agent_a").agent("agent_b")
    fs.contract("agent_a", "agent_b", fields={"required": "string"})
    result = fs.validate("agent_a", "agent_b", {})

    buf = io.StringIO()
    with redirect_stdout(buf):
        print_validation(result, verbose=True)
    out = buf.getvalue()
    assert "agent_a" in out
    assert "agent_b" in out


def test_report_empty():
    r = subprocess.run(
        [sys.executable, "-m", "agentpact.cli", "report"],
        capture_output=True, text=True, timeout=10,
        cwd=os.path.dirname(os.path.abspath(__file__)),
    )
    assert r.returncode == 0
    assert "no" in r.stdout.lower() or "audit" in r.stdout.lower()


TESTS = [test_cli_help, test_watch_mode_script, test_ansi_formatting, test_report_empty]

if __name__ == "__main__":
    passed = failed = 0
    print("=" * 50)
    print("  Failsafe CLI Tests")
    print("=" * 50)
    print()
    for t in TESTS:
        try:
            t()
            print(f"\u2705 {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"\u274c {t.__name__}: {e}")
            failed += 1
    print()
    print("=" * 50)
    print(f"  Results: {passed} passed, {failed} failed, {len(TESTS)} total")
    print("=" * 50)
    sys.exit(1 if failed else 0)
