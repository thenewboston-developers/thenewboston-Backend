from django.utils import timezone


def apply_elapsed_time(match, *, now=None):
    now = now or timezone.now()
    elapsed_ms = int((now - match.turn_started_at).total_seconds() * 1000)
    if elapsed_ms < 0:
        elapsed_ms = 0

    if match.active_player_id == match.player_a_id:
        remaining = match.clock_a_remaining_ms - elapsed_ms
        match.clock_a_remaining_ms = max(remaining, 0)
    else:
        remaining = match.clock_b_remaining_ms - elapsed_ms
        match.clock_b_remaining_ms = max(remaining, 0)

    return remaining, now


def switch_turn(match, *, now=None):
    now = now or timezone.now()
    match.active_player = match.player_b if match.active_player_id == match.player_a_id else match.player_a
    match.turn_started_at = now
    match.turn_number += 1
    return now


def touch_turn(match, *, now=None):
    now = now or timezone.now()
    match.turn_started_at = now
    return now
