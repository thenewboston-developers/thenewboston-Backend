import os
import subprocess
import sys
from pathlib import Path


def test_fresh_worker_registers_and_schedules_video_poker_timeout():
    """A fresh worker must discover the task without pytest's imports registering it first."""
    root = Path(__file__).resolve().parents[3]
    result = subprocess.run(
        [
            sys.executable,
            '-c',
            'from thenewboston.project.celery import app; '
            'app.loader.import_default_modules(); '
            "assert 'tasks.expire_video_poker_hands' in app.tasks, 'Worker is missing the Video Poker timeout task'; "
            "scheduled = {entry['task'] for entry in app.conf.beat_schedule.values()}; "
            "assert 'tasks.expire_video_poker_hands' in scheduled, 'Beat does not schedule Video Poker timeouts'",
        ],
        cwd=root,
        env={**os.environ, 'PYTHONPATH': str(root)},
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
