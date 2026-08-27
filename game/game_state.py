import copy
import random

from .buildings import ALL_TYPES
from .events import CHALLENGE_MODE, create_challenge_state, ensure_challenge_state

ARCADE_MODE = 'arcade'
FREEPLAY_MODE = 'freeplay'
VALID_MODES = {ARCADE_MODE, FREEPLAY_MODE, CHALLENGE_MODE}
LIMITED_MODES = {ARCADE_MODE, CHALLENGE_MODE}

BONUS_TASK_TEMPLATES = [
    # Hao Ying: these optional challenge definitions give players extra
    # score or coin rewards when they meet specific objectives mid-run.
    {
        'template_id': 'residential_expansion',
        'title': 'Residential Expansion',
        'description': 'Build 5 Residential buildings within the next 8 turns.',
        'goal_type': 'building_count',
        'goal_value': 5,
        'building_type': 'R',
        'turn_limit': 8,
        'reward_kind': 'score',
        'reward_value': 20,
        'reward_text': '+20 score',
    },
    {
        'template_id': 'industrial_growth',
        'title': 'Industrial Growth',
        'description': 'Construct 3 Industry buildings within the next 6 turns.',
        'goal_type': 'building_count',
        'goal_value': 3,
        'building_type': 'I',
        'turn_limit': 6,
        'reward_kind': 'coins',
        'reward_value': 10,
        'reward_text': '+10 coins',
    },
    {
        'template_id': 'green_city_initiative',
        'title': 'Green City Initiative',
        'description': 'Build 4 Park buildings before the challenge expires.',
        'goal_type': 'building_count',
        'goal_value': 4,
        'building_type': 'O',
        'turn_limit': 7,
        'reward_kind': 'score',
        'reward_value': 15,
        'reward_text': '+15 score',
    },
    {
        'template_id': 'road_network',
        'title': 'Road Network',
        'description': 'Create a connected road network of at least 6 Road tiles.',
        'goal_type': 'road_network',
        'goal_value': 6,
        'building_type': '*',
        'turn_limit': 8,
        'reward_kind': 'score',
        'reward_value': 15,
        'reward_text': '+15 score',
    },
    {
        'template_id': 'commercial_district',
        'title': 'Commercial District',
        'description': 'Build 4 Commercial buildings within the next 8 turns.',
        'goal_type': 'building_count',
        'goal_value': 4,
        'building_type': 'C',
        'turn_limit': 8,
        'reward_kind': 'coins',
        'reward_value': 15,
        'reward_text': '+15 coins',
    },
    {
        'template_id': 'industrial_powerhouse',
        'title': 'Industrial Powerhouse',
        'description': 'Build 8 Industry buildings within 10 turns.',
        'goal_type': 'building_count',
        'goal_value': 8,
        'building_type': 'I',
        'turn_limit': 10,
        'reward_kind': 'coins',
        'reward_value': 25,
        'reward_text': '+25 coins',
    },
    {
        'template_id': 'residential_mega',
        'title': 'Residential Mega Complex',
        'description': 'Construct 10 Residential buildings within 12 turns.',
        'goal_type': 'building_count',
        'goal_value': 10,
        'building_type': 'R',
        'turn_limit': 12,
        'reward_kind': 'score',
        'reward_value': 40,
        'reward_text': '+40 score',
    },
    {
        'template_id': 'park_paradise',
        'title': 'Park Paradise',
        'description': 'Build 6 Park buildings in the next 9 turns.',
        'goal_type': 'building_count',
        'goal_value': 6,
        'building_type': 'O',
        'turn_limit': 9,
        'reward_kind': 'score',
        'reward_value': 25,
        'reward_text': '+25 score',
    },
    {
        'template_id': 'commercial_boom',
        'title': 'Commercial Boom',
        'description': 'Build 7 Commercial buildings in 10 turns.',
        'goal_type': 'building_count',
        'goal_value': 7,
        'building_type': 'C',
        'turn_limit': 10,
        'reward_kind': 'coins',
        'reward_value': 30,
        'reward_text': '+30 coins',
    },
    {
        'template_id': 'massive_road_network',
        'title': 'Massive Road Network',
        'description': 'Create a connected road network with 12+ Road tiles.',
        'goal_type': 'road_network',
        'goal_value': 12,
        'building_type': '*',
        'turn_limit': 10,
        'reward_kind': 'score',
        'reward_value': 30,
        'reward_text': '+30 score',
    },
    {
        'template_id': 'mixed_metropolis',
        'title': 'Mixed Metropolis',
        'description': 'Build at least 3 of each building type (R, I, C, O) within 12 turns.',
        'goal_type': 'mixed_buildings',
        'goal_value': 3,
        'building_type': 'RICO',
        'turn_limit': 12,
        'reward_kind': 'score',
        'reward_value': 50,
        'reward_text': '+50 score',
    },
    {
        'template_id': 'balanced_growth',
        'title': 'Balanced Growth',
        'description': 'Build 5 buildings with balanced split between Industry and Commercial.',
        'goal_type': 'balanced_split',
        'goal_value': 5,
        'building_type': 'IC',
        'turn_limit': 8,
        'reward_kind': 'coins',
        'reward_value': 20,
        'reward_text': '+20 coins',
    },
]


def _count_buildings(board, building_type):
    return sum(cell == building_type for row in board for cell in row)


def _connected_road_network_size(board):
    rows = len(board)
    cols = len(board[0]) if board else 0
    visited = set()
    best_size = 0

    for r in range(rows):
        for c in range(cols):
            if board[r][c] != '*' or (r, c) in visited:
                continue
            stack = [(r, c)]
            visited.add((r, c))
            size = 0
            while stack:
                current_r, current_c = stack.pop()
                size += 1
                for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    nr, nc = current_r + dr, current_c + dc
                    if 0 <= nr < rows and 0 <= nc < cols and board[nr][nc] == '*' and (nr, nc) not in visited:
                        visited.add((nr, nc))
                        stack.append((nr, nc))
            best_size = max(best_size, size)

    return best_size


def _get_task_progress(task, state):
    template_id = task['template_id']
    if template_id == 'residential_expansion' or template_id == 'residential_mega':
        return _count_buildings(state.board, 'R')
    if template_id == 'industrial_growth' or template_id == 'industrial_powerhouse':
        return _count_buildings(state.board, 'I')
    if template_id == 'green_city_initiative' or template_id == 'park_paradise':
        return _count_buildings(state.board, 'O')
    if template_id == 'road_network' or template_id == 'massive_road_network':
        return _connected_road_network_size(state.board)
    if template_id == 'commercial_district' or template_id == 'commercial_boom':
        return _count_buildings(state.board, 'C')
    if template_id == 'mixed_metropolis':
        r_count = _count_buildings(state.board, 'R')
        i_count = _count_buildings(state.board, 'I')
        c_count = _count_buildings(state.board, 'C')
        o_count = _count_buildings(state.board, 'O')
        return min(r_count, i_count, c_count, o_count)
    if template_id == 'balanced_growth':
        i_count = _count_buildings(state.board, 'I')
        c_count = _count_buildings(state.board, 'C')
        return min(i_count, c_count)
    return 0


def _create_bonus_task(template, state):
    expires_at_turn = state.turn + template['turn_limit']
    return {
        'template_id': template['template_id'],
        'title': template['title'],
        'description': template['description'],
        'goal_value': template['goal_value'],
        'reward_kind': template['reward_kind'],
        'reward_value': template['reward_value'],
        'reward_text': template['reward_text'],
        'progress': 0,
        'expires_at_turn': expires_at_turn,
        'status': 'active',
        'remaining_turns': template['turn_limit'],
    }


def _refresh_bonus_task_pool(state):
    if state.mode not in LIMITED_MODES:
        state.bonus_tasks = []
        state.completed_bonus_task_ids = []
        return []

    all_tasks = getattr(state, 'bonus_tasks', [])
    finished_tasks = [task for task in all_tasks if task.get('status') in {'completed', 'expired'}]
    active_tasks = [task for task in all_tasks if task.get('status') == 'active']

    # CHANGE: bonus tasks are now dealt out in fixed-size batches
    # (bonus_task_total, default 5) instead of filling the whole pool
    # (previously up to 12) up front and then topping up one slot at a
    # time as each task finished. Now, as long as ANY task from the
    # current batch is still active, we leave the pool alone. Only once
    # every task in the batch has resolved (completed or expired) do we
    # shuffle the remaining not-yet-seen templates and deal a brand new
    # batch. This makes the UI show exactly one batch of up to
    # bonus_task_total tasks at a time, and a template is never repeated
    # once it has appeared in a previous batch (whether it was completed
    # or expired).
    if not active_tasks:
        used_ids = {task['template_id'] for task in finished_tasks}
        available_templates = [
            template for template in BONUS_TASK_TEMPLATES
            if template['template_id'] not in used_ids
        ]
        random.shuffle(available_templates)

        batch_size = getattr(state, 'bonus_task_total', 5)
        new_batch = available_templates[:batch_size]
        active_tasks = [_create_bonus_task(template, state) for template in new_batch]

        # CHANGE: bonus_tasks_dealt_total is the cumulative number of tasks
        # ever dealt out across all batches (5, then 10, then 15, ...). The
        # frontend progress bar ("X/Y completed") uses this instead of the
        # fixed per-batch size, so the denominator grows once a batch is
        # fully cleared and a new one is dealt — rather than resetting back
        # to 5 every time. Only increments when a NEW batch actually starts
        # (i.e. not on the very first call before any templates exist, and
        # not while the current batch is still in progress).
        if new_batch:
            state.bonus_tasks_dealt_total = getattr(state, 'bonus_tasks_dealt_total', 0) + len(new_batch)

    state.bonus_tasks = finished_tasks + active_tasks
    return state.bonus_tasks


def evaluate_bonus_tasks(state):
    if state.mode not in LIMITED_MODES:
        return []

    if not hasattr(state, 'bonus_tasks'):
        state.bonus_tasks = []
    if not hasattr(state, 'completed_bonus_task_ids'):
        state.completed_bonus_task_ids = []
    if not hasattr(state, 'bonus_task_total'):
        state.bonus_task_total = 5
    notifications = []
    completed_ids = set(state.completed_bonus_task_ids)
    updated_tasks = []

    for task in state.bonus_tasks:
        if task.get('status') in {'completed', 'expired'}:
            # FIX: keep already-finished tasks in the list instead of
            # dropping them, so the UI can still display them.
            updated_tasks.append(task)
            continue

        task['progress'] = _get_task_progress(task, state)
        task['remaining_turns'] = max(0, int(task.get('expires_at_turn', state.turn + 1)) - state.turn)

        if task['progress'] >= task['goal_value'] and task['template_id'] not in completed_ids:
            task['status'] = 'completed'
            task['completed_turn'] = state.turn
            completed_ids.add(task['template_id'])
            state.completed_bonus_task_ids = list(completed_ids)

            # Hao Ying: completing an optional task immediately awards its
            # configured bonus so players can raise their final result.
            if task['reward_kind'] == 'coins':
                state.coins += int(task['reward_value'])
                notifications.append(f'🎯 Bonus task complete: {task["title"]} (+{task["reward_value"]} coins)')
            else:
                state.score += int(task['reward_value'])
                notifications.append(f'🎯 Bonus task complete: {task["title"]} (+{task["reward_value"]} score)')
            updated_tasks.append(task)
            continue

        if state.turn > int(task.get('expires_at_turn', state.turn + 1)):
            task['status'] = 'expired'
            task['completed_turn'] = state.turn
            updated_tasks.append(task)
            continue

        updated_tasks.append(task)

    state.bonus_tasks = updated_tasks
    _refresh_bonus_task_pool(state)
    return notifications


class GameState:
    def __init__(self, mode=ARCADE_MODE):
        if mode not in VALID_MODES:
            raise ValueError('Unknown game mode')

        self.mode = mode
        self.turn = 1
        self.score = 0
        self.board_score = 0
        self.buildings_count = 0
        self.completed_challenges = []
        self.bonus_task_total = 5  # CHANGE: size of each batch of bonus tasks shown at once (was 12)
        self.bonus_tasks_dealt_total = 0  # CHANGE: cumulative tasks ever dealt out, grows 5 -> 10 -> 15...
        self.completed_bonus_task_ids = []
        self.bonus_tasks = []

        if mode in LIMITED_MODES:
            self.coins = 16
            self.grid_size = 20
            self.board = [[None] * 20 for _ in range(20)]
            self.offered_buildings = self._random_pair()

            if mode == CHALLENGE_MODE:
                self.challenge_state = create_challenge_state()
                self.challenge_income = 0
                self.challenge_upkeep = 0

            _refresh_bonus_task_pool(self)
        else:
            self.coins = 0          # unused in Free Play (unlimited)
            self.grid_size = 5
            self.board = [[None] * 5 for _ in range(5)]
            self.profit = 0
            self.upkeep = 0
            self.loss_turns = 0
            self.expansion_count = 0

    def _random_pair(self):
        return random.sample(ALL_TYPES, 2)

    def to_dict(self):
        data = {
            'mode': self.mode,
            'turn': self.turn,
            'score': self.score,
            'board_score': getattr(self, 'board_score', 0),
            'grid_size': self.grid_size,
            'board': self.board,
            'buildings_count': self.buildings_count,
            'completed_challenges': list(self.completed_challenges),
            'bonus_task_total': getattr(self, 'bonus_task_total', 5),
            'bonus_tasks_dealt_total': getattr(self, 'bonus_tasks_dealt_total', 0),
            'bonus_tasks': copy.deepcopy(getattr(self, 'bonus_tasks', [])),
            'completed_bonus_task_ids': list(getattr(self, 'completed_bonus_task_ids', [])),
        }

        if self.mode in LIMITED_MODES:
            data['coins'] = self.coins
            data['offered_buildings'] = self.offered_buildings

            if self.mode == CHALLENGE_MODE:
                ensure_challenge_state(self)
                data['challenge_state'] = copy.deepcopy(self.challenge_state)
        else:
            data['profit'] = self.profit
            data['upkeep'] = self.upkeep
            data['net'] = self.profit - self.upkeep
            data['loss_turns'] = self.loss_turns
            data['expansion_count'] = self.expansion_count

        return data

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValueError('Invalid save data')

        mode = data.get('mode', ARCADE_MODE)
        if mode not in VALID_MODES:
            mode = ARCADE_MODE

        state = cls.__new__(cls)
        state.mode = mode
        state.turn = max(1, int(data.get('turn', 1)))
        state.score = int(data.get('score', 0))
        state.board_score = int(data.get('board_score', 0))
        state.board = data.get('board')
        if not isinstance(state.board, list) or not state.board or not isinstance(state.board[0], list):
            raise ValueError('Invalid board data in save file')
        column_count = len(state.board[0])
        if column_count == 0 or any(not isinstance(row, list) or len(row) != column_count for row in state.board):
            raise ValueError('Invalid board shape in save file')

        state.grid_size = len(state.board)
        state.buildings_count = sum(bool(cell) for row in state.board for cell in row)
        if 'board_score' not in data:
            # Older saves stored only the displayed score, which previously
            # matched the live board valuation. Use it as the starting
            # baseline so loading an old save does not immediately re-award
            # the whole board.
            state.board_score = max(0, state.score)
        completed_challenges = data.get('completed_challenges', [])
        state.completed_challenges = list(completed_challenges) if isinstance(completed_challenges, list) else []
        state.bonus_task_total = int(data.get('bonus_task_total', 5))
        state.bonus_tasks = copy.deepcopy(data.get('bonus_tasks', [])) if isinstance(data.get('bonus_tasks', []), list) else []
        if 'bonus_tasks_dealt_total' in data:
            state.bonus_tasks_dealt_total = int(data.get('bonus_tasks_dealt_total', 0))
        else:
            # Older save files predate this field. Best-effort backfill:
            # assume everything currently sitting in bonus_tasks (active +
            # finished) has already been "dealt", so the progress bar
            # doesn't regress to a smaller total on next load.
            state.bonus_tasks_dealt_total = len(state.bonus_tasks) or state.bonus_task_total
        completed_bonus_ids = data.get('completed_bonus_task_ids', [])
        state.completed_bonus_task_ids = list(completed_bonus_ids) if isinstance(completed_bonus_ids, list) else []

        if state.mode in LIMITED_MODES:
            state.coins = max(0, int(data.get('coins', 16)))
            offered = data.get('offered_buildings', [])
            state.offered_buildings = [building for building in offered if building in ALL_TYPES]
            if len(state.offered_buildings) != 2:
                state.offered_buildings = random.sample(ALL_TYPES, 2)

            if state.mode == CHALLENGE_MODE:
                state.challenge_state = copy.deepcopy(data.get('challenge_state', create_challenge_state()))
                state.challenge_income = max(0, int(data.get('challenge_income', 0)))
                state.challenge_upkeep = max(0, int(data.get('challenge_upkeep', 0)))
                ensure_challenge_state(state)

            if not state.bonus_tasks:
                _refresh_bonus_task_pool(state)
        else:
            state.profit = int(data.get('profit', 0))
            state.upkeep = int(data.get('upkeep', 0))
            state.loss_turns = max(0, int(data.get('loss_turns', 0)))
            state.expansion_count = max(0, int(data.get('expansion_count', 0)))

        return state
