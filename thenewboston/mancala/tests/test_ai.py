from random import Random

import pytest

from thenewboston.mancala import ai
from thenewboston.mancala.ai import choose_pit
from thenewboston.mancala.rules import initial_board, is_finished, leader, legal_pits, opponent, sow


def board(host, guest, host_store=0, guest_store=0):
    return [*host, host_store, *guest, guest_store]


def play(host_level, guest_level, seed):
    rng = Random(seed)
    state, side = initial_board(), 'host' if seed % 2 else 'guest'
    while not is_finished(state):
        pit = choose_pit(state, side, host_level if side == 'host' else guest_level, rng)
        state, move = sow(state, side, pit)
        if not move['extra_turn']:
            side = opponent(side)
    return leader(state)


@pytest.mark.parametrize('difficulty', ai.DIFFICULTIES)
@pytest.mark.parametrize('side', ['host', 'guest'])
def test_every_level_only_chooses_pits_that_hold_stones(difficulty, side):
    rng = Random(3)
    state = board([0, 3, 0, 1, 0, 6], [2, 0, 0, 5, 0, 1], host_store=15, guest_store=15)
    for _ in range(20):
        assert choose_pit(state, side, difficulty, rng) in legal_pits(state, side)


def test_the_only_legal_pit_is_played_and_an_empty_row_is_an_error():
    state = board([0, 0, 0, 0, 2, 0], [1, 1, 1, 1, 1, 1], host_store=20, guest_store=20)
    assert choose_pit(state, 'host', 'hard') == 4
    with pytest.raises(ValueError):
        choose_pit(board([0] * 6, [0] * 6, 24, 24), 'host', 'normal')
    with pytest.raises(ValueError):
        choose_pit(initial_board(), 'host', 'expert')


@pytest.mark.parametrize('difficulty', ['normal', 'hard'])
def test_thinking_levels_take_the_winning_capture(difficulty):
    # Pit 0 captures the 12 stones opposite its landing pit. Pit 3 lets them get away.
    state = board([1, 0, 0, 2, 0, 0], [0, 0, 0, 0, 12, 1], host_store=16, guest_store=16)
    assert choose_pit(state, 'host', difficulty, Random(1)) == 0


def test_stronger_levels_beat_weaker_ones():
    assert [play('normal', 'easy', seed) for seed in range(6)].count('host') >= 5
    assert [play('easy', 'hard', seed) for seed in range(6)].count('guest') >= 5
    assert [play('hard', 'normal', seed) for seed in range(6)].count('host') >= 5


def test_hard_stops_searching_when_its_budget_is_spent(monkeypatch):
    examined = []
    original = ai._search

    def counting(*args):
        examined.append(1)
        return original(*args)

    monkeypatch.setattr(ai, '_search', counting)
    assert choose_pit(initial_board(), 'host', 'hard', Random(2)) in range(6)
    # Each depth may overrun by the single position that discovers the budget is gone.
    assert len(examined) <= ai.SEARCH['hard'][1] + 1


def test_an_exhausted_budget_still_returns_a_legal_pit(monkeypatch):
    monkeypatch.setitem(ai.SEARCH, 'hard', (8, 0))
    assert choose_pit(initial_board(), 'guest', 'hard', Random(4)) in range(6)
