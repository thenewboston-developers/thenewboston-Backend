"""Computer strategy receives only its shots and publicly revealed sunk ships."""

from random import SystemRandom

from .rules import BOARD_SIZE, SHIP_LENGTHS, ship_cells


def choose_shot(shots, revealed_ships, difficulty='normal', rng=None):
    rng = rng or SystemRandom()
    fired = {(shot['row'], shot['column']) for shot in shots}
    available = {(row, column) for row in range(BOARD_SIZE) for column in range(BOARD_SIZE)} - fired
    if not available:
        raise ValueError('There are no unfired squares.')
    if difficulty == 'easy':
        return rng.choice(sorted(available))
    sunk_cells = {cell for ship in revealed_ships for cell in ship_cells(ship)}
    hits = {(shot['row'], shot['column']) for shot in shots if shot['result'] != 'miss'} - sunk_cells
    adjacent = {(row + dr, column + dc) for row, column in hits for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1))}
    if difficulty == 'normal':
        return rng.choice(sorted((adjacent & available) or available))
    blocked = {(shot['row'], shot['column']) for shot in shots if shot['result'] == 'miss'} | sunk_cells
    sunk_ids = {ship['id'] for ship in revealed_ships}
    scores = dict.fromkeys(available, 0)
    for ship_id in SHIP_LENGTHS.keys() - sunk_ids:
        for orientation in ('horizontal', 'vertical'):
            for row in range(BOARD_SIZE):
                for column in range(BOARD_SIZE):
                    cells = set(ship_cells({'id': ship_id, 'row': row, 'column': column, 'orientation': orientation}))
                    if any(r >= BOARD_SIZE or c >= BOARD_SIZE for r, c in cells) or cells & blocked:
                        continue
                    # Favor explanations of observed hits without consulting the hidden fleet.
                    weight = 1 + 20 * len(cells & hits)
                    for cell in cells & available:
                        scores[cell] += weight
    best = max(scores.values())
    return rng.choice(sorted(cell for cell, score in scores.items() if score == best))
