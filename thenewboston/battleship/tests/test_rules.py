from copy import deepcopy
from random import Random

import pytest

from thenewboston.battleship.ai import choose_shot
from thenewboston.battleship.rules import SHIP_LENGTHS, random_fleet, resolve_shot, ship_cells, validate_fleet


def fleet():
    return [
        {'id': ship_id, 'row': row * 2, 'column': 0, 'orientation': 'horizontal'}
        for row, ship_id in enumerate(SHIP_LENGTHS)
    ]


@pytest.mark.parametrize('seed', range(20))
def test_random_fleets_have_exactly_seventeen_non_overlapping_squares(seed):
    ships = random_fleet(Random(seed))
    assert validate_fleet(ships) == ships
    assert len({cell for ship in ships for cell in ship_cells(ship)}) == 17


@pytest.mark.parametrize('change', ['duplicate', 'overlap', 'bounds', 'short', 'diagonal', 'bad_id', 'boolean'])
def test_bad_placements_rejected(change):
    ships = fleet()
    if change == 'duplicate':
        ships[1]['id'] = ships[0]['id']
    elif change == 'overlap':
        ships[1]['row'] = 0
    elif change == 'bounds':
        ships[0]['column'] = 9
    elif change == 'short':
        ships.pop()
    elif change == 'diagonal':
        ships[0]['orientation'] = 'diagonal'
    elif change == 'bad_id':
        ships[0]['id'] = []
    else:
        ships[0]['row'] = True
    with pytest.raises(ValueError):
        validate_fleet(ships)


def test_hit_does_not_reveal_ship_identity_and_last_hit_sinks():
    shots = []
    ships = fleet()
    for row, column in ship_cells(ships[0]):
        shot, won = resolve_shot(ships, shots, row, column)
        shots.append(shot)
        assert not won
        if column < 4:
            assert shot == {'row': row, 'column': column, 'result': 'hit'}
        else:
            assert shot['result'] == 'sunk'
            assert shot['ship_id'] == 'carrier'
    with pytest.raises(ValueError):
        resolve_shot(ships, shots, 0, 0)


@pytest.mark.parametrize('difficulty', ['easy', 'normal', 'hard'])
def test_computer_completes_a_game_using_only_public_observations(difficulty):
    ships = random_fleet(Random(72))
    shots, revealed = [], []
    for _ in range(100):
        row, column = choose_shot(deepcopy(shots), deepcopy(revealed), difficulty, Random(len(shots)))
        shot, won = resolve_shot(ships, shots, row, column)
        shots.append(shot)
        if shot['result'] == 'sunk':
            revealed.append(next(ship for ship in ships if ship['id'] == shot['ship_id']))
        if won:
            break
    assert won
    assert len({(shot['row'], shot['column']) for shot in shots}) == len(shots)
    assert len(revealed) == 5


def test_normal_ai_hunts_next_to_observed_hits():
    shots = [{'row': 4, 'column': 4, 'result': 'hit'}, {'row': 3, 'column': 4, 'result': 'miss'}]
    assert choose_shot(shots, [], 'normal', Random(1)) in {(5, 4), (4, 3), (4, 5)}
