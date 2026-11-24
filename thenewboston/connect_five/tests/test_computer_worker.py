import os
import subprocess
import sys
from pathlib import Path

from django.conf import settings


def test_fresh_worker_registers_computer_task_and_recovery_sweep():
    root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [
            sys.executable,
            '-c',
            'from thenewboston.project.celery import app; '
            'app.loader.import_default_modules(); '
            "assert {'tasks.play_connect_five_computer_turn', 'tasks.sweep_connect_five_timeouts'} <= app.tasks.keys()",
        ],
        cwd=root,
        env={**os.environ, 'PYTHONPATH': str(root)},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert settings.CELERY_BEAT_SCHEDULE['sweep_connect_five_timeouts']['schedule'] == 15
