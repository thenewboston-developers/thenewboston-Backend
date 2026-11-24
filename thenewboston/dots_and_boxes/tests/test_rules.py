import random

import pytest

from thenewboston.dots_and_boxes.ai import SEARCH_NODE_LIMIT, TurnSearch, _hard_line, choose_line, plan_turn
from thenewboston.dots_and_boxes.rules import (
    SIZES,
    apply_move,
    box_lines,
    initial_boxes,
    initial_lines,
    line_boxes,
    line_count,
    opponent,
)


def drawn(size, *lines):
    """A board with only these lines drawn, all by blue."""
    board = initial_lines(size)
    for line in lines:
        board[line] = 1
    return board


def corridors(size=4):
    """Every horizontal line drawn: each row is a chain of ``size`` boxes, with no safe line left."""
    return drawn(size, *range(size * (size + 1)))


def play_turn(size, lines, boxes, side, difficulty):
    """Plan one side's whole turn and draw it; every line but the last must complete a box."""
    planned = plan_turn(size, lines, difficulty)
    for index, line in enumerate(planned):
        lines[:], boxes[:], completed = apply_move(size, lines, boxes, side, line)
        assert bool(completed) or index == len(planned) - 1
    assert not completed or 0 not in lines
    return planned


@pytest.mark.parametrize('size,lines', [(3, 24), (4, 40), (5, 60)])
def test_every_line_borders_one_or_two_boxes_and_every_box_has_four_lines(size, lines):
    assert line_count(size) == lines
    assert len(initial_lines(size)) == lines and len(initial_boxes(size)) == size * size
    assert sorted(len(boxes) for boxes in line_boxes(size)).count(1) == 4 * size
    assert all(len(set(edges)) == 4 for edges in box_lines(size))
    # Each box appears once per side, and lines on the inside are shared by exactly two boxes.
    assert sum(len(boxes) for boxes in line_boxes(size)) == 4 * size * size


def test_line_numbering_matches_the_documented_layout():
    # 3 by 3: horizontals 0-11 from the top edge down, then verticals 12-23 row by row.
    assert box_lines(3)[0] == (0, 3, 12, 13)
    assert box_lines(3)[4] == (4, 7, 17, 18)
    assert box_lines(3)[8] == (8, 11, 22, 23)
    assert line_boxes(3)[4] == (1, 4)
    assert line_boxes(3)[12] == (0,)


def test_fourth_side_claims_the_box_for_the_player_who_drew_it():
    lines, boxes = initial_lines(3), initial_boxes(3)
    for line in (0, 3, 12):
        lines, boxes, completed = apply_move(3, lines, boxes, 'blue', line)
        assert completed == [] and boxes == initial_boxes(3)
    lines, boxes, completed = apply_move(3, lines, boxes, 'red', 13)
    assert completed == [0]
    assert boxes[0] == 2 and lines[13] == 2 and lines[0] == 1


def test_one_line_can_complete_two_boxes():
    # Everything around boxes 0 and 1 except the line they share.
    lines = drawn(3, 0, 1, 3, 4, 12, 14)
    _, boxes, completed = apply_move(3, lines, initial_boxes(3), 'blue', 13)
    assert completed == [0, 1] and boxes[:2] == [1, 1]


def test_moves_do_not_change_the_position_they_were_given():
    lines, boxes = initial_lines(3), initial_boxes(3)
    apply_move(3, lines, boxes, 'blue', 5)
    assert lines == initial_lines(3) and boxes == initial_boxes(3)


@pytest.mark.parametrize('line', [-1, 24, 40, '3', 3.0, True, None, [3]])
def test_malformed_or_out_of_range_lines_are_rejected(line):
    with pytest.raises(ValueError):
        apply_move(3, initial_lines(3), initial_boxes(3), 'blue', line)


def test_a_drawn_line_cannot_be_drawn_again():
    with pytest.raises(ValueError):
        apply_move(3, drawn(3, 7), initial_boxes(3), 'red', 7)


@pytest.mark.parametrize('size', SIZES)
@pytest.mark.parametrize('difficulty', ['easy', 'normal', 'hard'])
def test_computer_plays_whole_games_legally_and_every_box_is_claimed_once(size, difficulty):
    random.seed(size * 10 + len(difficulty))
    lines, boxes = initial_lines(size), initial_boxes(size)
    side = 'blue'
    while 0 in lines:
        assert play_turn(size, lines, boxes, side, difficulty)
        side = opponent(side)
    assert 0 not in boxes
    assert boxes.count(1) + boxes.count(2) == size * size


@pytest.mark.parametrize('difficulty', ['easy', 'normal', 'hard'])
def test_every_level_takes_a_box_that_is_on_offer(difficulty):
    # Box 0 has three sides; plenty of safe lines remain elsewhere.
    assert choose_line(4, drawn(4, 0, 4, 20), difficulty) == 21


@pytest.mark.parametrize('difficulty', ['normal', 'hard'])
def test_normal_and_hard_do_not_hand_over_a_box_while_a_safe_line_exists(difficulty):
    # Box 0 has two sides: its two open sides (3 and 13) are the only unsafe lines.
    lines = drawn(3, 0, 12)
    for _ in range(40):
        assert choose_line(3, lines, difficulty) not in {3, 13}


@pytest.mark.parametrize('difficulty', ['normal', 'hard'])
def test_forced_to_give_something_away_the_computer_gives_the_least(difficulty):
    # The top row is a chain of three; the lower two rows are full except single box 8,
    # which has two open sides (its top, line 8, and its right edge, line 23).
    lines = [1] * line_count(3)
    for line in (12, 13, 14, 15, 8, 23):
        lines[line] = 0
    for _ in range(20):
        assert choose_line(3, lines, difficulty) in {8, 23}


def test_hard_gives_up_the_last_two_boxes_of_a_chain_to_keep_control():
    # Four chains of four. Blue opened the top one, so red can take all four, or take two and
    # leave two with a single line (24), which makes blue open the next chain as well.
    lines = corridors()
    boxes = initial_boxes(4)
    lines[20] = 1
    played = play_turn(4, lines, boxes, 'red', 'hard')
    assert played == [21, 22, 24]
    assert boxes[:4] == [2, 2, 0, 0] and lines[23] == 0


def test_normal_takes_the_whole_chain():
    lines = corridors()
    boxes = initial_boxes(4)
    lines[20] = 1
    played = play_turn(4, lines, boxes, 'red', 'normal')
    assert played[:4] == [21, 22, 23, 24]
    assert boxes[:4] == [2, 2, 2, 2]


def test_hard_rules_of_thumb_agree_when_the_position_is_too_large_to_search():
    lines = corridors()
    for line in (20, 21, 22):
        lines[line] = 1
    mask = sum(1 << line for line, owner in enumerate(lines) if owner)
    # No nodes to spend: the search is skipped and the rule of thumb decides.
    assert _hard_line(mask, 4, TurnSearch(nodes=0)) == 24


def test_hard_takes_the_last_two_boxes_when_nothing_else_is_left_to_win():
    lines = [1] * line_count(4)
    lines[23] = lines[24] = 0
    mask = sum(1 << line for line, owner in enumerate(lines) if owner)
    assert _hard_line(mask, 4, TurnSearch(nodes=0)) == 23
    assert choose_line(4, lines, 'hard') == 23


def test_hard_does_not_search_an_open_board():
    search = TurnSearch()
    choose_line(5, initial_lines(5), 'hard', search)
    assert search.nodes == SEARCH_NODE_LIMIT and not search.solved


def test_search_never_spends_more_than_its_budget():
    random.seed(7)
    lines, boxes = initial_lines(5), initial_boxes(5)
    side = 'blue'
    while 0 in lines:
        search = TurnSearch()
        while 0 in lines:
            line = choose_line(5, lines, 'hard', search)
            assert search.nodes >= -1
            lines, boxes, completed = apply_move(5, lines, boxes, side, line)
            if not completed:
                break
        side = opponent(side)
