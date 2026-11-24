"""Pure Battleship rules. Coordinates are zero-based; adjacent ships are allowed."""

from random import SystemRandom

BOARD_SIZE = 10
SHIP_LENGTHS = {'carrier': 5, 'battleship': 4, 'cruiser': 3, 'submarine': 3, 'destroyer': 2}


def opponent(side):
    return 'guest' if side == 'host' else 'host'


def ship_cells(ship):
    length = SHIP_LENGTHS[ship['id']]
    vertical = ship['orientation'] == 'vertical'
    return [
        (ship['row'] + (index if vertical else 0), ship['column'] + (0 if vertical else index))
        for index in range(length)
    ]


def validate_fleet(ships):
    if not isinstance(ships, list) or len(ships) != len(SHIP_LENGTHS):
        raise ValueError('Place all five ships.')
    ids, occupied, normalized = set(), set(), []
    for ship in ships:
        if (
            not isinstance(ship, dict)
            or not isinstance(ship.get('id'), str)
            or ship['id'] not in SHIP_LENGTHS
            or ship['id'] in ids
        ):
            raise ValueError('Place each ship exactly once.')
        if ship.get('orientation') not in ('horizontal', 'vertical'):
            raise ValueError('Choose a horizontal or vertical orientation.')
        if any(type(ship.get(key)) is not int or not 0 <= ship[key] < BOARD_SIZE for key in ('row', 'column')):
            raise ValueError('Ships must stay inside the 10 by 10 board.')
        clean = {key: ship[key] for key in ('id', 'row', 'column', 'orientation')}
        cells = set(ship_cells(clean))
        if any(row >= BOARD_SIZE or column >= BOARD_SIZE for row, column in cells):
            raise ValueError('Ships must stay inside the 10 by 10 board.')
        if cells & occupied:
            raise ValueError('Ships cannot overlap.')
        ids.add(ship['id'])
        occupied.update(cells)
        normalized.append(clean)
    return normalized


def random_fleet(rng=None):
    rng = rng or SystemRandom()
    occupied, ships = set(), []
    for ship_id, length in SHIP_LENGTHS.items():
        candidates = []
        for orientation in ('horizontal', 'vertical'):
            for row in range(BOARD_SIZE if orientation == 'horizontal' else BOARD_SIZE - length + 1):
                for column in range(BOARD_SIZE - length + 1 if orientation == 'horizontal' else BOARD_SIZE):
                    ship = {'id': ship_id, 'row': row, 'column': column, 'orientation': orientation}
                    if not set(ship_cells(ship)) & occupied:
                        candidates.append(ship)
        ship = rng.choice(candidates)
        ships.append(ship)
        occupied.update(ship_cells(ship))
    return ships


def resolve_shot(ships, shots, row, column):
    if type(row) is not int or type(column) is not int or not 0 <= row < BOARD_SIZE or not 0 <= column < BOARD_SIZE:
        raise ValueError('Choose a square inside the board.')
    fired = {(shot['row'], shot['column']) for shot in shots}
    if (row, column) in fired:
        raise ValueError('You already fired at this square.')
    shot = {'row': row, 'column': column, 'result': 'miss'}
    fired.add((row, column))
    for ship in ships:
        cells = set(ship_cells(ship))
        if (row, column) in cells:
            shot['result'] = 'sunk' if cells <= fired else 'hit'
            if shot['result'] == 'sunk':
                shot['ship_id'] = ship['id']
            break
    won = all(set(ship_cells(ship)) <= fired for ship in ships)
    return shot, won


def sunk_ships(ships, shots):
    ids = {shot['ship_id'] for shot in shots if shot.get('ship_id')}
    return [ship for ship in ships if ship['id'] in ids]
