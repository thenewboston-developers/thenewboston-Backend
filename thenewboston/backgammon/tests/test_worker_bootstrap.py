import os
import subprocess
import sys
from pathlib import Path


def test_fresh_worker_registers_backgammon_tasks():
    """Exercise Celery's real bootstrap without pytest's prior task imports."""
    root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [
            sys.executable,
            '-c',
            'from thenewboston.project.celery import app; '
            'app.loader.import_default_modules(); '
            "expected = {'tasks.play_backgammon_computer_turn', 'tasks.sweep_backgammon_matches'}; "
            'missing = expected.difference(app.tasks); '
            "assert not missing, f'Worker did not register backgammon tasks: {sorted(missing)}'",
        ],
        cwd=root,
        env={**os.environ, 'PYTHONPATH': str(root)},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
