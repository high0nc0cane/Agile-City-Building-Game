import math
import random
from datetime import datetime, timezone
from .economy import freeplay_economy
from .scoring import compute_total_score

def check_events_and_challenges(game_state):
    """
    Evaluates the board for completed challenges and random events.
    Returns a list of notification strings to display to the user.
    """
    notifications = []
    
    # Ensure backward compatibility with old save files
    if not hasattr(game_state, 'completed_challenges'):
        game_state.completed_challenges = []
        
    # NEW: Create a persistent tracker for flat bonus points
    if not hasattr(game_state, 'bonus_score'):
        game_state.bonus_score = 0

    # ---------------------------------------------------------
    # 1. OPTIONAL CHALLENGES (Milestones)
    # ---------------------------------------------------------
    # Challenge 1: Urban Planner (Build 5 Residential)
    res_count = sum(1 for r in range(len(game_state.board)) for c in range(len(game_state.board[0])) if game_state.board[r][c] == 'R')
    if res_count >= 5 and '5_res' not in game_state.completed_challenges:
        game_state.completed_challenges.append('5_res')
        game_state.bonus_score += 20
        notifications.append("🏆 Challenge Complete: Urban Planner! (+20 Score)")

    # Challenge 2: Metropolis (Build 15 Total Buildings)
    total_buildings = sum(bool(cell) for row in game_state.board for cell in row)
    if total_buildings >= 15 and '15_buildings' not in game_state.completed_challenges:
        game_state.completed_challenges.append('15_buildings')
        game_state.bonus_score += 50
        notifications.append("🏆 Challenge Complete: Metropolis! (+50 Score)")

    # ---------------------------------------------------------
    # 2. RANDOM CITY EVENTS (15% chance per turn)
    # ---------------------------------------------------------
    if random.random() < 0.15: 
        event_roll = random.choice(['boom', 'recession', 'grant'])
        
        if event_roll == 'boom':
            game_state.bonus_score += 15
            notifications.append("📰 Event: Economic Boom! (+15 Score)")
            
        elif event_roll == 'recession':
            if getattr(game_state, 'mode', None) == 'arcade':
                game_state.coins = max(1, game_state.coins - 2)
                notifications.append("📰 Event: Minor Recession! (-2 Coins)")
                
        elif event_roll == 'grant':
            if getattr(game_state, 'mode', None) == 'arcade':
                game_state.coins += 3
                notifications.append("📰 Event: Government Grant! (+3 Coins)")

    return notifications


CHALLENGE_MODE = 'challenge'
BUILDING_COST_INCREASE_INTERVAL = 5

EVENT_START_TURN = 5
EVENT_CHANCE = 0.30
EVENT_COOLDOWN_TURNS = 2
MAX_EVENT_HISTORY = 50

TAX_DELAY_TURNS = 5
TORNADO_DELAY_TURNS = 3
TEMP_EFFECT_DURATION_TURNS = 3

TAX_AMOUNT = 10
TORNADO_MAX_BUILDINGS = 6
EARTHQUAKE_MAX_BUILDINGS = 3
FIRE_MAX_NEIGHBOURS = 2
CONSTRUCTION_COST_INCREASE = 2
RECESSION_INCOME_MULTIPLIER = 0.50
MAINTENANCE_COST_MULTIPLIER = 1.50
RELIEF_GRANT_AMOUNT = 8

EVENT_DEFINITIONS = {
    'tax_collector': {
        'title': 'Tax Collector',
        'category': 'City Event',
        'kind': 'scheduled',
        'weight': 18,
        'delay_turns': TAX_DELAY_TURNS,
        'popup_type': 'warning',
        'major_disaster': False,
    },
    'construction_shortage': {
        'title': 'Construction Shortage',
        'category': 'Economic Event',
        'kind': 'temporary',
        'weight': 18,
        'duration_turns': TEMP_EFFECT_DURATION_TURNS,
        'popup_type': 'warning',
        'major_disaster': False,
    },
    'economic_recession': {
        'title': 'Economic Recession',
        'category': 'Economic Event',
        'kind': 'temporary',
        'weight': 18,
        'duration_turns': TEMP_EFFECT_DURATION_TURNS,
        'popup_type': 'warning',
        'major_disaster': False,
    },
    'maintenance_surge': {
        'title': 'Maintenance Surge',
        'category': 'Economic Event',
        'kind': 'temporary',
        'weight': 18,
        'duration_turns': TEMP_EFFECT_DURATION_TURNS,
        'popup_type': 'warning',
        'major_disaster': False,
    },
    'earthquake': {
        'title': 'Earthquake',
        'category': 'Disaster',
        'kind': 'immediate',
        'weight': 12,
        'popup_type': 'disaster',
        'major_disaster': True,
    },
    'fire_outbreak': {
        'title': 'Fire Outbreak',
        'category': 'Disaster',
        'kind': 'immediate',
        'weight': 10,
        'popup_type': 'disaster',
        'major_disaster': True,
    },
    'tornado': {
        'title': 'Tornado Warning',
        'category': 'Disaster',
        'kind': 'scheduled',
        'weight': 4,
        'delay_turns': TORNADO_DELAY_TURNS,
        'popup_type': 'warning',
        'major_disaster': True,
    },
    'emergency_relief_grant': {
        'title': 'Emergency Relief Grant',
        'category': 'Positive Event',
        'kind': 'immediate',
        'weight': 2,
        'popup_type': 'normal',
        'major_disaster': False,
    },
}

def create_challenge_state():
    """Return a fresh, JSON-serialisable state for Challenges Mode."""
    return {
        'last_event_turn': None,
        'last_event_type': None,
        'cooldown_until_turn': 0,
        'pending_events': [],
        'active_effects': [],
        'event_history': [],
        'next_event_id': 1,
        'last_cost_increase_turn': 0,
    }


def _utc_timestamp():
    return datetime.now(timezone.utc).isoformat()


def _safe_int(value, default=0, minimum=None):
    try:
        result = int(value)
    except (TypeError, ValueError):
        result = default
    if minimum is not None:
        result = max(minimum, result)
    return result


def ensure_challenge_state(game_state):
    """Repair missing or malformed event fields from older save files."""
    raw_state = getattr(game_state, 'challenge_state', None)
    if not isinstance(raw_state, dict):
        raw_state = create_challenge_state()

    defaults = create_challenge_state()
    for key, value in defaults.items():
        if key not in raw_state:
            raw_state[key] = value

    raw_state['pending_events'] = [
        event for event in raw_state.get('pending_events', [])
        if isinstance(event, dict)
    ]
    raw_state['active_effects'] = [
        effect for effect in raw_state.get('active_effects', [])
        if isinstance(effect, dict)
    ]
    raw_state['event_history'] = [
        entry for entry in raw_state.get('event_history', [])
        if isinstance(entry, dict)
    ][-MAX_EVENT_HISTORY:]
    raw_state['next_event_id'] = _safe_int(raw_state.get('next_event_id'), 1, 1)
    raw_state['cooldown_until_turn'] = _safe_int(raw_state.get('cooldown_until_turn'), 0, 0)
    raw_state['last_cost_increase_turn'] = _safe_int(raw_state.get('last_cost_increase_turn'), 0, 0)

    last_event_turn = raw_state.get('last_event_turn')
    raw_state['last_event_turn'] = (
        _safe_int(last_event_turn, 0, 0) if last_event_turn is not None else None
    )
    last_event_type = raw_state.get('last_event_type')
    raw_state['last_event_type'] = last_event_type if last_event_type in EVENT_DEFINITIONS else None

    current_turn = _safe_int(getattr(game_state, 'turn', 1), 1, 1)

    valid_pending = []
    for event in raw_state['pending_events']:
        event_type = event.get('type')
        if event_type not in EVENT_DEFINITIONS:
            continue
        announced_turn = _safe_int(event.get('announced_turn'), max(1, current_turn - 1), 1)
        due_turn = _safe_int(event.get('due_turn'), announced_turn + 1, announced_turn + 1)
        event['id'] = str(event.get('id') or _next_event_id(raw_state, event_type))
        event['type'] = event_type
        event['title'] = str(event.get('title') or EVENT_DEFINITIONS[event_type]['title'])
        event['category'] = str(event.get('category') or EVENT_DEFINITIONS[event_type]['category'])
        event['status'] = 'upcoming'
        event['announced_turn'] = announced_turn
        event['due_turn'] = due_turn
        event['announced_at'] = str(event.get('announced_at') or _utc_timestamp())
        event['executed'] = bool(event.get('executed', False))
        
        if event_type == 'tax_collector':
            default_message = f'City taxes of {TAX_AMOUNT} coins will be collected.'
            default_effect = f'{TAX_AMOUNT} coins will be deducted on turn {due_turn}.'
        else:
            default_message = 'A tornado may strike the city.'
            default_effect = f'Up to {TORNADO_MAX_BUILDINGS} occupied buildings may be destroyed on turn {due_turn}.'
            
        event['message'] = str(event.get('message') or default_message)
        event['effect'] = str(event.get('effect') or default_effect)
        if not event['executed']:
            valid_pending.append(event)
    raw_state['pending_events'] = valid_pending

    valid_effects = []
    for effect in raw_state['active_effects']:
        effect_type = effect.get('type')
        if effect_type not in EVENT_DEFINITIONS:
            continue
        start_turn = _safe_int(effect.get('start_turn'), current_turn, 1)
        end_turn = _safe_int(
            effect.get('end_turn'),
            start_turn + TEMP_EFFECT_DURATION_TURNS - 1,
            start_turn,
        )
        effect['id'] = str(effect.get('id') or _next_event_id(raw_state, effect_type))
        effect['type'] = effect_type
        effect['title'] = str(effect.get('title') or EVENT_DEFINITIONS[effect_type]['title'])
        effect['category'] = str(effect.get('category') or EVENT_DEFINITIONS[effect_type]['category'])
        effect['status'] = 'active'
        effect['start_turn'] = start_turn
        effect['end_turn'] = end_turn
        effect['announced_turn'] = _safe_int(effect.get('announced_turn'), max(1, start_turn - 1), 1)
        effect['announced_at'] = str(effect.get('announced_at') or _utc_timestamp())
        effect['expiry_shown'] = bool(effect.get('expiry_shown', False))
        valid_effects.append(effect)
    raw_state['active_effects'] = valid_effects

    game_state.challenge_state = raw_state
    update_event_countdowns(game_state)
    return raw_state


def _next_event_id(challenge_state, event_type):
    next_id = _safe_int(challenge_state.get('next_event_id'), 1, 1)
    challenge_state['next_event_id'] = next_id + 1
    return f'{event_type}-{next_id}'


def _history_entry(event_id, event_type, title, category, status, message, turn, occurred_at=None):
    return {
        'id': str(event_id),
        'type': event_type,
        'title': title,
        'category': category,
        'status': status,
        'message': message,
        'turn': _safe_int(turn, 1, 1),
        'occurred_at': occurred_at or _utc_timestamp(),
    }


def _append_history(game_state, entry):
    challenge_state = ensure_challenge_state(game_state)
    challenge_state['event_history'].append(entry)
    challenge_state['event_history'] = challenge_state['event_history'][-MAX_EVENT_HISTORY:]


def _popup(event_id, title, category, description, effect, popup_type='normal', turns_remaining=None):
    return {
        'id': str(event_id),
        'title': title,
        'category': category,
        'description': description,
        'effect': effect,
        'popup_type': popup_type,
        'turns_remaining': turns_remaining,
    }


def get_turn_cost_increase(game_state):
    if getattr(game_state, 'mode', None) != CHALLENGE_MODE:
        return 0
    current_turn = _safe_int(getattr(game_state, 'turn', 1), 1, 1)
    return max(0, (current_turn - 1) // BUILDING_COST_INCREASE_INTERVAL)


def _process_turn_cost_increase(game_state, completed_turn):
    challenge_state = ensure_challenge_state(game_state)
    completed_turn = _safe_int(completed_turn, 1, 1)
    last_increase_turn = _safe_int(challenge_state.get('last_cost_increase_turn'), 0, 0)

    if completed_turn < BUILDING_COST_INCREASE_INTERVAL:
        return []
    if completed_turn % BUILDING_COST_INCREASE_INTERVAL != 0:
        return []
    if completed_turn <= last_increase_turn:
        return []

    challenge_state['last_cost_increase_turn'] = completed_turn
    new_cost = get_placement_cost(game_state)
    next_increase_turn = completed_turn + BUILDING_COST_INCREASE_INTERVAL
    event_id = _next_event_id(challenge_state, 'construction-cost-rise')
    title = 'Construction Costs Rising'
    category = 'Economic Event'
    description = f'All building costs increased by 1 coin after turn {completed_turn}.'
    effect = f'Buildings now cost {new_cost} coins each. The next increase happens after turn {next_increase_turn}.'

    _append_history(
        game_state,
        _history_entry(
            event_id,
            'construction-cost-rise',
            title,
            category,
            'occurred',
            f'Building costs increased to {new_cost} coins after turn {completed_turn}.',
            completed_turn,
        ),
    )
    return [_popup(event_id, title, category, description, effect, 'warning')]


def update_event_countdowns(game_state):
    challenge_state = getattr(game_state, 'challenge_state', None)
    if not isinstance(challenge_state, dict):
        return

    next_turn = _safe_int(getattr(game_state, 'turn', 1), 1, 1)
    for event in challenge_state.get('pending_events', []):
        event['remaining_turns'] = max(0, _safe_int(event.get('due_turn'), next_turn) - next_turn + 1)

    for effect in challenge_state.get('active_effects', []):
        start_turn = _safe_int(effect.get('start_turn'), next_turn, 1)
        end_turn = _safe_int(effect.get('end_turn'), start_turn, start_turn)
        if next_turn < start_turn:
            effect['turns_remaining'] = end_turn - start_turn + 1
        else:
            effect['turns_remaining'] = max(0, end_turn - next_turn + 1)


def get_active_effect(game_state, effect_type, turn=None):
    if getattr(game_state, 'mode', None) != CHALLENGE_MODE:
        return None
    challenge_state = ensure_challenge_state(game_state)
    target_turn = _safe_int(turn if turn is not None else getattr(game_state, 'turn', 1), 1, 1)
    for effect in challenge_state['active_effects']:
        if (
            effect.get('type') == effect_type
            and _safe_int(effect.get('start_turn'), target_turn) <= target_turn
            and target_turn <= _safe_int(effect.get('end_turn'), target_turn)
        ):
            return effect
    return None


def get_placement_cost(game_state):
    """Return the live building placement cost without changing the base Arcade cost."""
    base_cost = 1 + get_turn_cost_increase(game_state)
    if get_active_effect(game_state, 'construction_shortage'):
        return base_cost + CONSTRUCTION_COST_INCREASE
    return base_cost


def apply_income_modifier(game_state, positive_income, turn=None):
    income = max(0, _safe_int(positive_income, 0, 0))
    if income and get_active_effect(game_state, 'economic_recession', turn):
        # Floor keeps the result as a whole coin and never changes expenses.
        return math.floor(income * RECESSION_INCOME_MULTIPLIER)
    return income


def calculate_maintenance_charge(game_state, board, turn=None):
    """Use the project's existing upkeep formula only while Maintenance Surge is active."""
    if not get_active_effect(game_state, 'maintenance_surge', turn):
        return 0
    _, base_upkeep = freeplay_economy(board)
    return math.ceil(max(0, base_upkeep) * MAINTENANCE_COST_MULTIPLIER)


def recalculate_after_destruction(game_state):
    board = game_state.board
    game_state.buildings_count = sum(1 for row in board for cell in row if cell)
    game_state.board_score = compute_total_score(board)


def add_board_score_earned(game_state):
    """Accumulate only newly-earned board points and never subtract score."""
    latest_board_score = compute_total_score(game_state.board)
    previous_board_score = max(0, _safe_int(getattr(game_state, 'board_score', 0), 0, 0))
    earned_points = max(0, latest_board_score - previous_board_score)
    game_state.score = max(0, _safe_int(getattr(game_state, 'score', 0), 0, 0)) + earned_points
    game_state.board_score = latest_board_score
    return earned_points


def remove_buildings(game_state, coordinates):
    """Remove validated, occupied coordinates once and return what was removed."""
    board = game_state.board
    rows = len(board)
    cols = len(board[0]) if rows else 0
    removed = []
    seen = set()

    for coordinate in coordinates:
        if not isinstance(coordinate, (list, tuple)) or len(coordinate) != 2:
            continue
        row = _safe_int(coordinate[0], -1)
        col = _safe_int(coordinate[1], -1)
        if (row, col) in seen:
            continue
        seen.add((row, col))
        if 0 <= row < rows and 0 <= col < cols and board[row][col]:
            removed.append({'row': row, 'col': col, 'building': board[row][col]})
            board[row][col] = None

    recalculate_after_destruction(game_state)
    return removed


def _occupied_coordinates(board):
    return [
        (row, col)
        for row in range(len(board))
        for col in range(len(board[0]))
        if board[row][col]
    ]


def _destroy_random_buildings(game_state, maximum, rng):
    occupied = _occupied_coordinates(game_state.board)
    count = min(maximum, len(occupied))
    selected = rng.sample(occupied, count) if count else []
    return remove_buildings(game_state, selected)


def _execute_tax_collector(game_state, event):
    amount = min(TAX_AMOUNT, max(0, _safe_int(getattr(game_state, 'coins', 0), 0, 0)))
    game_state.coins = max(0, _safe_int(getattr(game_state, 'coins', 0), 0, 0) - TAX_AMOUNT)
    message = f'The tax collector collected {amount} coin{"s" if amount != 1 else ""}.'
    return message


def _execute_tornado(game_state, event, rng):
    removed = _destroy_random_buildings(game_state, TORNADO_MAX_BUILDINGS, rng)
    count = len(removed)
    return f'A tornado destroyed {count} building{"s" if count != 1 else ""}.'


def _execute_earthquake(game_state, rng):
    removed = _destroy_random_buildings(game_state, EARTHQUAKE_MAX_BUILDINGS, rng)
    count = len(removed)
    return f'An earthquake destroyed {count} building{"s" if count != 1 else ""}.'


def _execute_fire_outbreak(game_state, rng):
    occupied = _occupied_coordinates(game_state.board)
    if not occupied:
        recalculate_after_destruction(game_state)
        return 'A fire outbreak occurred, but there were no buildings to damage.'

    centre = rng.choice(occupied)
    row, col = centre
    rows = len(game_state.board)
    cols = len(game_state.board[0])
    neighbours = []
    for row_change, col_change in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        new_row = row + row_change
        new_col = col + col_change
        if (
            0 <= new_row < rows
            and 0 <= new_col < cols
            and game_state.board[new_row][new_col]
        ):
            neighbours.append((new_row, new_col))

    extra_count = min(FIRE_MAX_NEIGHBOURS, len(neighbours))
    selected_neighbours = rng.sample(neighbours, extra_count) if extra_count else []
    removed = remove_buildings(game_state, [centre, *selected_neighbours])
    count = len(removed)
    return f'A fire outbreak damaged part of the city and destroyed {count} building{"s" if count != 1 else ""}.'


def _schedule_event(game_state, event_type, completed_turn):
    challenge_state = ensure_challenge_state(game_state)
    definition = EVENT_DEFINITIONS[event_type]
    event_id = _next_event_id(challenge_state, event_type)
    due_turn = completed_turn + definition['delay_turns']

    event = {
        'id': event_id,
        'type': event_type,
        'title': definition['title'],
        'category': definition['category'],
        'status': 'upcoming',
        'announced_turn': completed_turn,
        'due_turn': due_turn,
        'remaining_turns': definition['delay_turns'],
        'announced_at': _utc_timestamp(),
        'executed': False,
        'major_disaster': definition['major_disaster'],
    }
    challenge_state['pending_events'].append(event)

    if event_type == 'tax_collector':
        description = f'City taxes of {TAX_AMOUNT} coins will be collected in {TAX_DELAY_TURNS} turns.'
        effect = f'{TAX_AMOUNT} coins will be deducted on turn {due_turn}.'
    else:
        description = f'A tornado may strike the city in {TORNADO_DELAY_TURNS} turns.'
        effect = f'Up to {TORNADO_MAX_BUILDINGS} occupied buildings may be destroyed on turn {due_turn}.'

    event['message'] = description
    event['effect'] = effect

    return _popup(
        event_id,
        definition['title'],
        definition['category'],
        description,
        effect,
        definition['popup_type'],
        definition['delay_turns'],
    )


def _start_temporary_effect(game_state, event_type, completed_turn):
    challenge_state = ensure_challenge_state(game_state)
    definition = EVENT_DEFINITIONS[event_type]
    event_id = _next_event_id(challenge_state, event_type)
    start_turn = completed_turn + 1
    end_turn = start_turn + definition['duration_turns'] - 1

    effect = {
        'id': event_id,
        'type': event_type,
        'title': definition['title'],
        'category': definition['category'],
        'status': 'active',
        'announced_turn': completed_turn,
        'start_turn': start_turn,
        'end_turn': end_turn,
        'turns_remaining': definition['duration_turns'],
        'announced_at': _utc_timestamp(),
        'expiry_shown': False,
    }

    if event_type == 'construction_shortage':
        effect['modifier_value'] = CONSTRUCTION_COST_INCREASE
        description = f'All buildings cost {CONSTRUCTION_COST_INCREASE} extra coins for the next {TEMP_EFFECT_DURATION_TURNS} turns.'
        effect_text = f'Placement cost becomes {1 + CONSTRUCTION_COST_INCREASE} coins from turn {start_turn} to turn {end_turn}.'
    elif event_type == 'economic_recession':
        effect['modifier_value'] = RECESSION_INCOME_MULTIPLIER
        description = f'Positive city income is reduced by 50% for the next {TEMP_EFFECT_DURATION_TURNS} turns.'
        effect_text = f'Only positive income is reduced from turn {start_turn} to turn {end_turn}.'
    else:
        effect['modifier_value'] = MAINTENANCE_COST_MULTIPLIER
        description = f'City maintenance costs are increased by 50% for the next {TEMP_EFFECT_DURATION_TURNS} turns.'
        effect_text = f'The existing upkeep formula is charged at 150% from turn {start_turn} to turn {end_turn}.'

    effect['message'] = description
    challenge_state['active_effects'].append(effect)
    return _popup(
        event_id,
        definition['title'],
        definition['category'],
        description,
        effect_text,
        definition['popup_type'],
        definition['duration_turns'],
    )


def _execute_immediate_event(game_state, event_type, completed_turn, rng):
    challenge_state = ensure_challenge_state(game_state)
    definition = EVENT_DEFINITIONS[event_type]
    event_id = _next_event_id(challenge_state, event_type)

    if event_type == 'earthquake':
        message = _execute_earthquake(game_state, rng)
        effect = f'Up to {EARTHQUAKE_MAX_BUILDINGS} occupied buildings were selected safely.'
    elif event_type == 'fire_outbreak':
        message = _execute_fire_outbreak(game_state, rng)
        effect = 'The selected building and up to two occupied orthogonal neighbours were removed.'
    else:
        game_state.coins = max(0, _safe_int(getattr(game_state, 'coins', 0), 0, 0)) + RELIEF_GRANT_AMOUNT
        message = f'The city received an emergency relief grant of {RELIEF_GRANT_AMOUNT} coins.'
        effect = f'{RELIEF_GRANT_AMOUNT} coins were added immediately.'

    _append_history(
        game_state,
        _history_entry(
            event_id,
            event_type,
            definition['title'],
            definition['category'],
            'disaster' if definition['category'] == 'Disaster' else 'occurred',
            message,
            completed_turn,
        ),
    )
    return _popup(
        event_id,
        definition['title'],
        definition['category'],
        message,
        effect,
        definition['popup_type'],
    )


def _execute_due_events(game_state, completed_turn, rng):
    challenge_state = ensure_challenge_state(game_state)
    notifications = []
    remaining_pending = []

    for event in challenge_state['pending_events']:
        due_turn = _safe_int(event.get('due_turn'), completed_turn + 1, 1)
        if due_turn > completed_turn:
            remaining_pending.append(event)
            continue
        if event.get('executed'):
            continue

        event['executed'] = True
        event_type = event.get('type')
        definition = EVENT_DEFINITIONS.get(event_type)
        if not definition:
            continue

        if event_type == 'tax_collector':
            message = _execute_tax_collector(game_state, event)
            status = 'occurred'
            effect = f'Coins are now {game_state.coins}.'
        elif event_type == 'tornado':
            message = _execute_tornado(game_state, event, rng)
            status = 'disaster'
            effect = 'The board, building count and score were recalculated.'
        else:
            continue

        _append_history(
            game_state,
            _history_entry(
                event['id'],
                event_type,
                definition['title'],
                definition['category'],
                status,
                message,
                completed_turn,
            ),
        )
        notifications.append(
            _popup(
                event['id'],
                definition['title'],
                definition['category'],
                message,
                effect,
                'disaster' if event_type == 'tornado' else 'normal',
            )
        )
        challenge_state['last_event_turn'] = completed_turn
        challenge_state['cooldown_until_turn'] = max(
            challenge_state['cooldown_until_turn'],
            completed_turn + EVENT_COOLDOWN_TURNS,
        )

    challenge_state['pending_events'] = remaining_pending
    return notifications


def _expire_temporary_effects(game_state, completed_turn):
    challenge_state = ensure_challenge_state(game_state)
    notifications = []
    remaining_effects = []

    expiry_messages = {
        'construction_shortage': 'Construction costs have returned to normal.',
        'economic_recession': 'The city economy has recovered.',
        'maintenance_surge': 'City maintenance costs have returned to normal.',
    }

    for effect in challenge_state['active_effects']:
        end_turn = _safe_int(effect.get('end_turn'), completed_turn, 1)
        if end_turn > completed_turn:
            remaining_effects.append(effect)
            continue

        event_type = effect.get('type')
        definition = EVENT_DEFINITIONS.get(event_type)
        if not definition:
            continue
        message = expiry_messages.get(event_type, f'{definition["title"]} has ended.')

        if not effect.get('expiry_shown'):
            effect['expiry_shown'] = True
            _append_history(
                game_state,
                _history_entry(
                    effect['id'],
                    event_type,
                    definition['title'],
                    definition['category'],
                    'expired',
                    message,
                    completed_turn,
                ),
            )
            notifications.append(
                _popup(
                    effect['id'],
                    definition['title'],
                    definition['category'],
                    message,
                    'The temporary modifier is no longer applied.',
                    'normal',
                )
            )

    challenge_state['active_effects'] = remaining_effects
    return notifications


def _weighted_event_choice(game_state, completed_turn, rng):
    challenge_state = ensure_challenge_state(game_state)
    last_event_type = challenge_state.get('last_event_type')
    pending_types = {event.get('type') for event in challenge_state['pending_events']}
    pending_major_due_turns = {
        _safe_int(event.get('due_turn'), 0, 0)
        for event in challenge_state['pending_events']
        if event.get('major_disaster')
    }

    available = []
    weights = []
    for event_type, definition in EVENT_DEFINITIONS.items():
        if event_type == last_event_type:
            continue
        if event_type in pending_types:
            continue
        if definition['kind'] == 'temporary' and get_active_effect(game_state, event_type):
            continue
        if event_type == 'tornado':
            proposed_due_turn = completed_turn + definition['delay_turns']
            if proposed_due_turn in pending_major_due_turns:
                continue
        available.append(event_type)
        weights.append(definition['weight'])

    if not available:
        return None
    return rng.choices(available, weights=weights, k=1)[0]


def process_challenge_turn(game_state, completed_turn, rng=None):
    """Advance scheduled/temporary events and possibly start one new event."""
    if getattr(game_state, 'mode', None) != CHALLENGE_MODE:
        return []

    rng = rng or random
    challenge_state = ensure_challenge_state(game_state)
    completed_turn = _safe_int(completed_turn, max(1, game_state.turn - 1), 1)
    notifications = []

    # Theresa: Challenge mode runs this after each completed turn to keep
    # random city events dynamic, so every playthrough can unfold differently.
    # Turn-based effects are processed once after the player completes a turn.
    notifications.extend(_process_turn_cost_increase(game_state, completed_turn))
    notifications.extend(_execute_due_events(game_state, completed_turn, rng))
    notifications.extend(_expire_temporary_effects(game_state, completed_turn))

    eligible_turn = completed_turn > EVENT_START_TURN
    cooldown_finished = completed_turn > challenge_state['cooldown_until_turn']
    if eligible_turn and cooldown_finished and rng.random() < EVENT_CHANCE:
        # Theresa: when the chance roll succeeds, one weighted city event is
        # chosen and applied so the player has to react to changing conditions.
        event_type = _weighted_event_choice(game_state, completed_turn, rng)
        if event_type:
            definition = EVENT_DEFINITIONS[event_type]
            if definition['kind'] == 'scheduled':
                notifications.append(_schedule_event(game_state, event_type, completed_turn))
            elif definition['kind'] == 'temporary':
                notifications.append(_start_temporary_effect(game_state, event_type, completed_turn))
            else:
                notifications.append(_execute_immediate_event(game_state, event_type, completed_turn, rng))

            challenge_state['last_event_turn'] = completed_turn
            challenge_state['last_event_type'] = event_type
            challenge_state['cooldown_until_turn'] = completed_turn + EVENT_COOLDOWN_TURNS

    update_event_countdowns(game_state)
    return notifications


def check_milestone_challenges(game_state):
    """Preserve the project's existing non-random milestone rewards."""
    if getattr(game_state, 'mode', None) != CHALLENGE_MODE:
        return []

    notifications = []
    completed = getattr(game_state, 'completed_challenges', None)
    if not isinstance(completed, list):
        completed = []
        game_state.completed_challenges = completed

    residential_count = sum(cell == 'R' for row in game_state.board for cell in row)
    if residential_count >= 5 and '5_res' not in completed:
        completed.append('5_res')
        game_state.score += 20
        notifications.append('🏆 Challenge Complete: Urban Planner! (+20 Score)')

    total_buildings = sum(bool(cell) for row in game_state.board for cell in row)
    if total_buildings >= 15 and '15_buildings' not in completed:
        completed.append('15_buildings')
        game_state.coins += 5
        notifications.append('🏆 Challenge Complete: Metropolis! (+5 Coins)')

    return notifications