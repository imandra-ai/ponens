"""Python's half of the three-way derivation check. See cli/tools/derivation_expected.py."""
import subprocess
import sys
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]


def test_python_derives_the_recorded_answer():
    r = subprocess.run([sys.executable, str(ROOT / "cli/tools/derivation_expected.py"), "--check"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
