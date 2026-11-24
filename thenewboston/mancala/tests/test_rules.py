from random import Random

import pytest

from thenewboston.mancala.rules import (
    STORE,
    TOTAL_STONES,
    initial_board,
    is_finished,
    leader,
    legal_pits,
    opponent,
    pit_index,
    sow,
)


def board(host, guest, host_store=0, guest_store=0):
    return [*host, host_store, *guest, guest_store]


def test_initial_board_has_four_stones_in_each_of_twelve_pits():
    assert initial_board() == [4, 4, 4, 4, 4, 4, 0, 4, 4, 4, 4, 4, 4, 0]
    assert sum(initial_board()) == TOTAL_STONES == 48
    assert legal_pits(initial_board(), 'host') == legal_pits(initial_board(), 'guest') == [0, 1, 2, 3, 4, 5]


def test_sowing_is_counter_clockwise_one_stone_per_pit_and_does_not_change_the_input():
    start = initial_board()
    after, move = sow(start, 'host', 0)
    assert start == initial_board()
    assert after == [0, 5, 5, 5, 5, 4, 0, 4, 4, 4, 4, 4, 4, 0]
    assert move == {
        'side': 'host',
        'pit': 0,
        'stones': 4,
        'last': 4,
        'captured': 0,
        'extra_turn': False,
        'swept': None,
    }


@pytest.mark.parametrize('side', ['host', 'guest'])
def test_last_stone_in_own_store_earns_another_turn(side):
    after, move = sow(initial_board(), side, 2)
    assert move['extra_turn']
    assert move['last'] == STORE[side]
    assert after[STORE[side]] == 1
    assert after[STORE[opponent(side)]] == 0


def test_sowing_passes_own_store_and_skips_the_opponents_store():
    after, move = sow(board([0, 0, 1, 0, 0, 10], [1, 1, 1, 1, 1, 1]), 'host', 5)
    assert after == board([1, 1, 2, 0, 0, 0], [2, 2, 2, 2, 2, 2], host_store=1)
    assert move['last'] == 2
    after, move = sow(board([1, 1, 1, 1, 1, 1], [0, 0, 1, 0, 0, 10]), 'guest', 5)
    assert after == board([2, 2, 2, 2, 2, 2], [1, 1, 2, 0, 0, 0], guest_store=1)
    assert move['last'] == pit_index('guest', 2)


def test_last_stone_in_own_empty_pit_captures_it_and_the_stones_opposite():
    after, move = sow(board([1, 0, 4, 4, 4, 4], [4, 4, 4, 4, 7, 4]), 'host', 0)
    assert move['captured'] == 8
    assert not move['extra_turn']
    assert after == board([0, 0, 4, 4, 4, 4], [4, 4, 4, 4, 0, 4], host_store=8)
    after, move = sow(board([4, 4, 4, 4, 3, 4], [1, 0, 4, 4, 4, 4]), 'guest', 0)
    assert move['captured'] == 4
    assert after == board([4, 4, 4, 4, 0, 4], [0, 0, 4, 4, 4, 4], guest_store=4)


def test_no_capture_when_the_opposite_pit_is_empty_or_the_pit_is_the_opponents():
    after, move = sow(board([1, 0, 4, 4, 4, 4], [4, 4, 4, 4, 0, 4]), 'host', 0)
    assert move['captured'] == 0
    assert after == board([0, 1, 4, 4, 4, 4], [4, 4, 4, 4, 0, 4])
    # The last stone lands in an empty pit on the opponent's side: nothing is captured.
    after, move = sow(board([4, 4, 4, 4, 4, 2], [0, 4, 4, 4, 4, 4]), 'host', 5)
    assert move['captured'] == 0
    assert after == board([4, 4, 4, 4, 4, 0], [1, 4, 4, 4, 4, 4], host_store=1)


def test_a_full_lap_ends_in_the_starting_pit_and_captures():
    after, move = sow(board([13, 1, 1, 1, 1, 1], [5, 5, 5, 5, 5, 5]), 'host', 0)
    assert move['last'] == 0
    # The last stone plus the six now opposite it, on top of the one sown into the store on the way round.
    assert move['captured'] == 7
    assert after == board([0, 2, 2, 2, 2, 2], [6, 6, 6, 6, 6, 0], host_store=8)


def test_game_ends_when_a_row_is_empty_and_the_other_row_goes_to_its_owner():
    after, move = sow(board([0, 0, 0, 0, 0, 1], [1, 2, 3, 0, 0, 0], host_store=20, guest_store=21), 'host', 5)
    assert move['swept'] == {'host': 0, 'guest': 6}
    assert not move['extra_turn']
    assert after == board([0] * 6, [0] * 6, host_store=21, guest_store=27)
    assert is_finished(after)
    assert leader(after) == 'guest'


def test_a_capture_that_empties_the_opponents_row_also_ends_the_game():
    after, move = sow(board([0, 0, 0, 1, 0, 5], [0, 3, 0, 0, 0, 0], host_store=19, guest_store=20), 'host', 3)
    assert move['captured'] == 4
    assert move['swept'] == {'host': 5, 'guest': 0}
    assert after == board([0] * 6, [0] * 6, host_store=28, guest_store=20)
    assert leader(after) == 'host'


def test_level_stores_have_no_leader():
    assert leader(board([0] * 6, [0] * 6, host_store=24, guest_store=24)) is None


@pytest.mark.parametrize('pit', [-1, 6, '2', 2.0, None, True])
def test_pits_outside_the_row_are_rejected(pit):
    with pytest.raises(ValueError):
        sow(initial_board(), 'host', pit)


def test_an_empty_pit_cannot_be_played():
    with pytest.raises(ValueError):
        sow(board([0, 4, 4, 4, 4, 4], [4] * 6, host_store=4), 'host', 0)


def test_random_games_always_finish_and_never_gain_or_lose_a_stone():
    rng = Random(7)
    for _ in range(200):
        state, side, turns = initial_board(), rng.choice(['host', 'guest']), 0
        while not is_finished(state):
            state, move = sow(state, side, rng.choice(legal_pits(state, side)))
            assert sum(state) == TOTAL_STONES
            assert all(count >= 0 for count in state)
            if not move['extra_turn']:
                side = opponent(side)
            turns += 1
            assert turns < 1000
        assert state[STORE['host']] + state[STORE['guest']] == TOTAL_STONES
