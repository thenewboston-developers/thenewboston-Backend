import os
import subprocess
import sys
from pathlib import Path

from django.conf import settings


def test_fresh_worker_registers_both_battleship_tasks():
    root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [
            sys.executable,
            '-c',
            'from thenewboston.project.celery import app; '
            'app.loader.import_default_modules(); '
            "expected = {'tasks.play_battleship_computer_turn', 'tasks.sweep_battleship_matches'}; "
            "assert expected <= app.tasks.keys(), f'Missing tasks: {expected - app.tasks.keys()}'",
        ],
        cwd=root,
        env={**os.environ, 'PYTHONPATH': str(root)},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert settings.CELERY_BEAT_SCHEDULE['sweep_battleship_matches']['task'] == 'tasks.sweep_battleship_matches'
