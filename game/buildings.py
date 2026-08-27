BUILDING_TYPES = {
    'R': {
        'name': 'Residential',
        'symbol': 'R',
        'description': '+1 per adj R/C · +2 per adj Park',
        'note': 'If adj to Industry → 1 pt only',
        'emoji': '🏠',
    },
    'I': {
        'name': 'Industry',
        'symbol': 'I',
        'description': '+1 per Industry in city',
        'note': 'Earns 1 coin per adj Residential',
        'emoji': '🏭',
    },
    'C': {
        'name': 'Commercial',
        'symbol': 'C',
        'description': '+1 per adj Commercial',
        'note': 'Earns 1 coin per adj Residential',
        'emoji': '🏪',
    },
    'O': {
        'name': 'Park',
        'symbol': 'O',
        'description': '+1 per adj Park',
        'note': 'Boosts adjacent Residential',
        'emoji': '🌳',
    },
    '*': {
        'name': 'Road',
        'symbol': '*',
        'description': '+1 per connected Road in row',
        'note': 'Longer rows score more',
        'emoji': '🛣',
    },
}

ALL_TYPES = list(BUILDING_TYPES.keys())
