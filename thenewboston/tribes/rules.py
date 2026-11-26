"""Versioned, provisional MVP balancing. Distances include diagonals."""

MAX_MEMBERS = 8
QUEUE_SECONDS = 86400
GATHER_CAPACITY = 5
UNIT_CAPACITY = 100
BUILDING_CAPACITY = 3
LAND = {
    'forest': {'resource': 'timber', 'price': 40},
    'iron_deposit': {'resource': 'iron_ore', 'price': 60},
    'coal_deposit': {'resource': 'coal', 'price': 50},
    'plains': {'resource': 'wheat', 'price': 30},
    'wilderness': {'resource': 'animal_hide', 'price': 40},
    'quarry': {'resource': 'stone', 'price': 40},
}
UNITS = {
    'infantry': {'damage': 10, 'range': 1},
    'catapult': {'damage': 80, 'range': 2},
    'trebuchet': {'damage': 200, 'range': 3},
}
DEFENSES = {'barricade': 30, 'stone_wall': 100}
BUILDINGS = {
    'lumber_camp': {'land': ['forest'], 'resource': 'timber'},
    'mine': {'land': ['iron_deposit', 'coal_deposit'], 'resource': 'mining'},
    'farm': {'land': ['plains'], 'resource': 'wheat'},
    'quarry_building': {'land': ['quarry'], 'resource': 'stone'},
    'furnace': {'land': list(LAND), 'resource': None},
    'workshop': {'land': list(LAND), 'resource': None},
}
RECIPES = {
    'lumber': {'inputs': {'timber': 2}, 'seconds': 120, 'facility': None},
    'iron_ingot': {'inputs': {'iron_ore': 2, 'coal': 1}, 'seconds': 180, 'facility': 'furnace'},
    'flour': {'inputs': {'wheat': 2}, 'seconds': 60, 'facility': None},
    'leather': {'inputs': {'animal_hide': 2}, 'seconds': 120, 'facility': None},
    'stone_block': {'inputs': {'stone': 2}, 'seconds': 120, 'facility': None},
    'pickaxe': {'inputs': {'iron_ingot': 3, 'lumber': 2}, 'seconds': 1800, 'facility': 'workshop'},
    'axe': {'inputs': {'iron_ingot': 2, 'lumber': 2}, 'seconds': 1800, 'facility': 'workshop'},
    'bread': {'inputs': {'flour': 2}, 'seconds': 60, 'facility': None},
    'infantry': {'inputs': {'iron_ingot': 2, 'leather': 1, 'bread': 2}, 'seconds': 900, 'facility': 'workshop'},
    'catapult': {'inputs': {'lumber': 20, 'iron_ingot': 10}, 'seconds': 7200, 'facility': 'workshop'},
    'trebuchet': {'inputs': {'lumber': 40, 'iron_ingot': 20, 'leather': 10}, 'seconds': 14400, 'facility': 'workshop'},
    'barricade': {'inputs': {'lumber': 5}, 'seconds': 900, 'facility': None},
    'stone_wall': {'inputs': {'stone_block': 10}, 'seconds': 1800, 'facility': None},
    'lumber_camp': {'inputs': {'timber': 20, 'stone': 10}, 'seconds': 3600, 'facility': None},
    'mine': {'inputs': {'timber': 20, 'stone': 20}, 'seconds': 3600, 'facility': None},
    'farm': {'inputs': {'timber': 15, 'stone': 10}, 'seconds': 3600, 'facility': None},
    'quarry_building': {'inputs': {'timber': 20, 'stone': 10}, 'seconds': 3600, 'facility': None},
    'furnace': {'inputs': {'stone': 30, 'timber': 15}, 'seconds': 3600, 'facility': None},
    'workshop': {'inputs': {'timber': 30, 'stone': 20}, 'seconds': 3600, 'facility': None},
}
ITEMS = list(dict.fromkeys([v['resource'] for v in LAND.values()] + list(RECIPES)))
TRADE_ITEMS = [item for item in ITEMS if item not in BUILDINGS and item not in UNITS and item not in DEFENSES]
OPENING_STOCK = {
    'timber': (100, 2),
    'iron_ore': (60, 4),
    'coal': (40, 3),
    'wheat': (125, 1),
    'animal_hide': (25, 4),
    'stone': (75, 2),
}


def distance(a, b):
    return max(abs(a['x'] - b['x']), abs(a['y'] - b['y']))


def catalog():
    return {
        'land': LAND,
        'recipes': RECIPES,
        'units': UNITS,
        'defenses': DEFENSES,
        'buildings': BUILDINGS,
        'items': ITEMS,
        'trade_items': TRADE_ITEMS,
        'market_items': [*TRADE_ITEMS, *UNITS, *DEFENSES],
        'work_order_items': ITEMS,
        'max_members': MAX_MEMBERS,
        'queue_seconds': QUEUE_SECONDS,
        'gather_capacity': GATHER_CAPACITY,
        'unit_capacity': UNIT_CAPACITY,
        'building_capacity': BUILDING_CAPACITY,
        'currency': 'TNB',
        'gather_rate': 10,
    }


def resolve_battle(tribes, units, plots):
    """Largest-remainder apportionment keeps every point of damage conserved."""
    rows = {
        t['id']: {
            'tribe_id': t['id'],
            'name': t['name'],
            'outgoing': 0,
            'incoming': 0,
            'raw_incoming': 0,
            'blocked': 0,
            'defense': 0,
            'score': 0,
            'attacks': [],
        }
        for t in tribes
    }
    locations = {p['id']: p for p in plots}
    attacks = []
    for unit in units:
        if unit['item'] in DEFENSES:
            rows[unit['tribe_id']]['defense'] += DEFENSES[unit['item']] * unit['quantity']
            continue
        target = unit.get('target_id')
        origin = locations.get(unit['plot_id'])
        if target not in rows or target == unit['tribe_id'] or not origin:
            continue
        if not any(p['tribe_id'] == target and distance(origin, p) <= UNITS[unit['item']]['range'] for p in plots):
            continue
        attack = {
            'unit_id': unit['id'],
            'tribe_id': unit['tribe_id'],
            'target_id': target,
            'controller_id': unit['controller_id'],
            'raw_damage': unit['quantity'] * UNITS[unit['item']]['damage'],
            'effective_damage': 0,
        }
        rows[target]['raw_incoming'] += attack['raw_damage']
        attacks.append(attack)
    for target, row in rows.items():
        incoming = [a for a in attacks if a['target_id'] == target]
        raw = row['raw_incoming']
        effective = max(0, raw - row['defense'])
        row['incoming'], row['blocked'] = effective, raw - effective
        allocated = 0
        for attack in incoming:
            attack['effective_damage'] = attack['raw_damage'] * effective // raw
            allocated += attack['effective_damage']
        order = sorted(incoming, key=lambda a: (-(a['raw_damage'] * effective % raw), a['unit_id']))
        for attack in order[: effective - allocated]:
            attack['effective_damage'] += 1
        for attack in incoming:
            rows[attack['tribe_id']]['outgoing'] += attack['effective_damage']
            row['attacks'].append(attack)
    for row in rows.values():
        row['score'] = row['outgoing'] - row['incoming']
    standings = sorted(rows.values(), key=lambda r: (-r['score'], r['tribe_id']))
    previous, rank = None, 0
    for index, row in enumerate(standings, 1):
        if row['score'] != previous:
            rank = index
        row['rank'], previous = rank, row['score']
    return {'standings': standings, 'attacks': attacks}
