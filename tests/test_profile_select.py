"""Run the dependency-free keyboard and form-value regressions when Node is available."""

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is needed for frontend regressions")
def test_profile_select_keyboard_and_form_values():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [shutil.which("node"), "--test", "tests/frontend/profile-select.test.cjs"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
