import json
import os
import random
from flask import Flask, render_template, request, jsonify, session, redirect
from account import account_menu, load_users, update_avatar
from game.statistics import generate_dashboard_stats

from game.game_state import GameState, VALID_MODES, LIMITED_MODES, FREEPLAY_MODE, evaluate_bonus_tasks
from game.economy import arcade_coin_income, freeplay_economy
from game.board import get_valid_cells, is_border_cell, expand_board
from game.buildings import ALL_TYPES
from game.events import (
    CHALLENGE_MODE,
    apply_income_modifier,
    calculate_maintenance_charge,
    check_milestone_challenges,
    check_events_and_challenges,
    add_board_score_earned,
    get_placement_cost,
    process_challenge_turn,
    recalculate_after_destruction,
    update_event_countdowns,
)

# Flask entry point for the Ngee Ann City web app.
# This file wires the browser routes to the underlying game/account modules
# and keeps the current in-memory game session in sync with the UI.
app = Flask(__name__)
app.secret_key = 'ngee-ann-city-2025'

# File locations for persistent data used by the app.
SAVES_DIR = os.path.join(os.path.dirname(__file__), 'saves')
HIGHSCORES_FILE = os.path.join(os.path.dirname(__file__), 'highscores.json')
HISTORY_FILE = os.path.join(os.path.dirname(__file__), 'score_history.json')
HIGHSCORE_LIMIT = 10
PROFILE_PICS_DIR = os.path.join(os.path.dirname(__file__), 'static', 'profile_pics')
ALLOWED_AVATAR_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}

os.makedirs(SAVES_DIR, exist_ok=True)
os.makedirs(PROFILE_PICS_DIR, exist_ok=True)

# The active game is stored in memory for the current server process.
current_game: GameState | None = None


def _is_limited_mode(mode):
    """Arcade and Challenge use coins/costs, unlike Free Play."""
    return mode in LIMITED_MODES


def _refresh_challenge_economy(game_state):
    """Recompute Challenge-only income/upkeep values shown in the UI."""
    if game_state.mode != CHALLENGE_MODE:
        return
    game_state.challenge_income = apply_income_modifier(
        game_state, arcade_coin_income(game_state.board), game_state.turn
    )
    game_state.challenge_upkeep = calculate_maintenance_charge(
        game_state, game_state.board, game_state.turn
    )


def _state_response(game_state, event_notifications=None, milestone_notifications=None):
    """Create the browser response without persisting calculated UI-only values."""
    update_event_countdowns(game_state)
    _refresh_challenge_economy(game_state)
    bonus_task_notifications = evaluate_bonus_tasks(game_state)

    state = game_state.to_dict()
    state['placement_cost'] = get_placement_cost(game_state) if _is_limited_mode(game_state.mode) else 0
    if game_state.mode == CHALLENGE_MODE:
        state['challenge_income'] = game_state.challenge_income
        state['challenge_upkeep'] = game_state.challenge_upkeep
    state['event_notifications'] = event_notifications or []
    state['notifications'] = list(milestone_notifications or [])
    state['bonus_task_notifications'] = bonus_task_notifications
    return state


def _limited_mode_game_over(game_state):
    """Limited modes end when the board is full or the next move is unaffordable."""
    board_full = all(cell for row in game_state.board for cell in row)
    return board_full or game_state.coins < get_placement_cost(game_state)


def _game_over_reason(game_state):
    """Return the exact end-game copy for the current state."""
    if game_state.mode == FREEPLAY_MODE:
        return 'The city made a loss for 20 consecutive turns.'
    if all(cell for row in game_state.board for cell in row):
        return 'The board is full!'
    if game_state.coins < get_placement_cost(game_state):
        return 'You ran out of coins!'
    return 'Game over.'


def _get_current_user():
    """Read and validate the logged-in user stored in the Flask session."""
    # Theresa: read the currently logged-in account from the session so the
    # app knows which player's profile and records are active right now.
    current_user = session.get('current_user')
    if not isinstance(current_user, dict):
        return None

    try:
        user_id = int(current_user.get('user_id'))
        username = str(current_user.get('username', '')).strip()
        password = str(current_user.get('password', ''))
        display_name = str(current_user.get('display_name', '')).strip()
        avatar_filename = str(current_user.get('avatar_filename', '')).strip()
    except (TypeError, ValueError):
        return None

    if user_id < 1 or not username or not password or not display_name:
        return None

    return {
        'user_id': user_id,
        'username': username,
        'password': password,
        'display_name': display_name,
        'avatar_filename': avatar_filename,
    }


def _set_current_user(user_data):
    """Persist the logged-in user back into the Flask session."""
    # Theresa: store the chosen account in the session after login or account
    # creation so the browser stays linked to that player's profile.
    session['current_user'] = user_data


def _public_user(user_data):
    """Return the safe subset of user data exposed to the frontend."""
    if not isinstance(user_data, dict):
        return None
    return {
        'user_id': user_data.get('user_id'),
        'username': user_data.get('username'),
        'display_name': user_data.get('display_name'),
        'avatar_url': _avatar_url(user_data.get('avatar_filename', '')),
    }


def _avatar_url(avatar_filename):
    """Convert an avatar filename into the static URL used by the browser."""
    filename = str(avatar_filename or '').strip()
    if not filename:
        return ''
    return f'/static/profile_pics/{filename}'


# ── Filename / player helpers ────────────────────────────────────────────────

def _sanitize(raw):
    """Whitelist alnum, dash, underscore, space. No dots -> no path traversal,
    and no path separators can survive this filter either."""
    return ''.join(c for c in (raw or '') if c.isalnum() or c in ('-', '_', ' ')).strip()


def _player_dir(raw_player, create=True):
    """Resolve (and optionally create) the per-account save folder.
    Returns None if no usable username was supplied."""
    safe = _sanitize(raw_player)
    if not safe:
        return None
    d = os.path.join(SAVES_DIR, safe)
    if create:
        os.makedirs(d, exist_ok=True)
    return d


# ── High score helpers ──────────────────────────────────────────────────────

def _load_hs():
    """Load the global top-score list from disk, tolerating empty/bad files."""
    if os.path.exists(HIGHSCORES_FILE):
        with open(HIGHSCORES_FILE, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if not content:
                return []
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return []
    return []


def _save_hs(scores):
    """Persist the global top-score list."""
    with open(HIGHSCORES_FILE, 'w', encoding='utf-8') as f:
        json.dump(scores, f, indent=2)


def _score_matches_user(existing_score, current_user):
    """Match a saved score entry back to a user using stable account fields."""
    if not isinstance(existing_score, dict) or not isinstance(current_user, dict):
        return False

    try:
        existing_user_id = existing_score.get('user_id')
        if existing_user_id is not None and int(existing_user_id) == int(current_user.get('user_id')):
            return True
    except (TypeError, ValueError):
        pass

    existing_username = str(existing_score.get('username') or existing_score.get('name') or '').strip().lower()
    if existing_username and existing_username == str(current_user.get('username', '')).strip().lower():
        return True

    existing_display_name = str(existing_score.get('display_name') or existing_score.get('name') or '').strip().lower()
    if existing_display_name and existing_display_name == str(current_user.get('display_name', '')).strip().lower():
        return True

    return False


def _score_entry(current_user, score, mode, turns):
    """Normalise score data into the shared structure used by history/highscores."""
    return {
        'user_id': current_user['user_id'],
        'username': current_user['username'],
        'display_name': current_user['display_name'],
        'avatar_url': _avatar_url(current_user.get('avatar_filename', '')),
        'name': current_user['display_name'],
        'score': score,
        'mode': mode,
        'turns': turns,
    }


def _user_index():
    """Build lookup tables for enriching score entries with fresh profile data."""
    users = load_users().get('users', [])
    by_id = {}
    by_username = {}
    for user in users:
        if not isinstance(user, dict):
            continue
        try:
            by_id[int(user.get('user_id', 0))] = user
        except (TypeError, ValueError):
            pass
        username = str(user.get('username', '')).strip().lower()
        if username:
            by_username[username] = user
    return by_id, by_username


def _with_avatar(entry, by_id, by_username):
    """Attach the latest display name/avatar info to an existing score entry."""
    if not isinstance(entry, dict):
        return entry

    matched_user = None
    try:
        user_id = entry.get('user_id')
        if user_id is not None:
            matched_user = by_id.get(int(user_id))
    except (TypeError, ValueError):
        matched_user = None

    if matched_user is None:
        username = str(entry.get('username') or entry.get('name') or '').strip().lower()
        if username:
            matched_user = by_username.get(username)

    if matched_user is None:
        return entry

    enriched = dict(entry)
    enriched['display_name'] = matched_user.get('display_name', entry.get('display_name') or entry.get('name'))
    enriched['username'] = matched_user.get('username', entry.get('username') or '')
    enriched['avatar_url'] = _avatar_url(matched_user.get('avatar_filename', ''))
    return enriched


def _qualifies(score, mode):
    """Check whether a score would currently fit into the mode's Top 10."""
    hs = [s for s in _load_hs() if s.get('mode') == mode]
    if len(hs) < HIGHSCORE_LIMIT:
        return True
    return score > min(s['score'] for s in hs)


def _add_hs(current_user, score, mode, turns):
    """Insert a user's best score into the mode leaderboard if it qualifies."""
    all_scores = _load_hs()
    mode_scores = [s for s in all_scores if s.get('mode') == mode and not _score_matches_user(s, current_user)]
    other_scores = [s for s in all_scores if s.get('mode') != mode]

    existing = [s for s in all_scores if s.get('mode') == mode and _score_matches_user(s, current_user)]
    if existing:
        best_existing_score = max(s.get('score', 0) for s in existing)
        if score <= best_existing_score:
            return False, None

    entry = _score_entry(current_user, score, mode, turns)
    # Hao Ying: insert the finished run into the correct mode leaderboard,
    # then trim the list back to the Top 10 so qualifying achievements are recorded.
    inserted = False
    for i, s in enumerate(mode_scores):
        if score > s.get('score', 0):
            mode_scores.insert(i, entry)
            inserted = True
            break
    if not inserted:
        mode_scores.append(entry)

    mode_scores = mode_scores[:HIGHSCORE_LIMIT]
    _save_hs(other_scores + mode_scores)

    if entry in mode_scores:
        rank = mode_scores.index(entry) + 1
        return True, rank
    return False, None


def _load_history():
    """Load the full score history for all accounts."""
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            content = f.read().strip()
            if not content:
                return []
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return []
    return []


def _save_history(entries):
    """Persist the full score history log."""
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(entries, f, indent=2)


def _add_history(current_user, score, mode, turns):
    """Append the finished run to the player's score history."""
    history = _load_history()
    history.append(_score_entry(current_user, score, mode, turns))
    _save_history(history)


# ── Routes ──────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    """Main menu / landing page."""
    current_user = _get_current_user()
    return render_template('menu.html', current_user=current_user, current_user_public=_public_user(current_user))


@app.route('/game')
def game():
    """Active game screen; requires a logged-in user."""
    current_user = _get_current_user()
    if not current_user:
        return redirect('/')
    return render_template('game.html', current_user=current_user, current_user_public=_public_user(current_user))


@app.route('/api/current_user', methods=['GET'])
def get_current_user_api():
    """Small helper endpoint for frontend account state refreshes."""
    current_user = _get_current_user()
    return jsonify({'current_user': _public_user(current_user)})


@app.route('/api/account', methods=['POST'])
def handle_account_action():
    """Create/login/logout account actions delegated to account.py."""
    data = request.get_json(force=True)
    action = str(data.get('action', '')).strip().lower()

    # Theresa: this single account endpoint handles create/login/logout
    # requests and updates the active player session in one place.
    try:
        user = account_menu(action, data)
    except ValueError as error:
        return jsonify({'error': str(error)}), 400

    if action == 'exit':
        session.pop('current_user', None)
        return jsonify({'success': True, 'current_user': None, 'message': 'Game closed.'})

    _set_current_user(user)
    message = 'Account created successfully.' if action == 'create' else f'Welcome back, {user["display_name"]}!'
    return jsonify({'success': True, 'current_user': _public_user(user), 'message': message})


@app.route('/api/account/avatar', methods=['POST'])
def upload_account_avatar():
    """Upload or replace the current user's profile picture."""
    current_user = _get_current_user()
    if not current_user:
        return jsonify({'error': 'No account is logged in'}), 400

    avatar_file = request.files.get('avatar')
    if avatar_file is None or not avatar_file.filename:
        return jsonify({'error': 'Please choose an image file first.'}), 400

    _, ext = os.path.splitext(avatar_file.filename)
    ext = ext.lower()
    if ext not in ALLOWED_AVATAR_EXTENSIONS:
        return jsonify({'error': 'Please upload PNG, JPG, JPEG, GIF, or WEBP.'}), 400

    avatar_filename = f"user-{current_user['user_id']}{ext}"
    avatar_path = os.path.join(PROFILE_PICS_DIR, avatar_filename)

    # Keep only one avatar file per user, regardless of previous extension.
    for existing_ext in ALLOWED_AVATAR_EXTENSIONS:
        existing_path = os.path.join(PROFILE_PICS_DIR, f"user-{current_user['user_id']}{existing_ext}")
        if existing_path != avatar_path and os.path.exists(existing_path):
            try:
                os.remove(existing_path)
            except OSError:
                pass

    avatar_file.save(avatar_path)

    try:
        updated_user = update_avatar(current_user['user_id'], avatar_filename)
    except ValueError as error:
        return jsonify({'error': str(error)}), 400

    _set_current_user(updated_user)
    return jsonify({
        'success': True,
        'current_user': _public_user(updated_user),
        'message': 'Profile picture updated.',
    })


@app.route('/instructions')
def instructions():
    """Static instructions/manual page."""
    return render_template('instructions.html')


@app.route('/api/new_game', methods=['POST'])
def new_game():
    """Start a fresh run in the requested mode."""
    global current_game
    if not _get_current_user():
        return jsonify({'error': 'No account is logged in'}), 400

    data = request.get_json(force=True)
    mode = str(data.get('mode', 'arcade')).strip().lower()
    if mode not in VALID_MODES:
        return jsonify({'error': 'Unknown game mode'}), 400

    current_game = GameState(mode)
    state = _state_response(current_game)
    state['valid_cells'] = get_valid_cells(current_game.board, True, mode)
    return jsonify(state)


@app.route('/api/state', methods=['GET'])
def get_state():
    """Return the current game snapshot used to render/resync the frontend."""
    if not current_game:
        return jsonify({'error': 'No game in progress'}), 400

    state = _state_response(current_game)
    is_first = current_game.buildings_count == 0
    state['valid_cells'] = get_valid_cells(current_game.board, is_first, current_game.mode)
    return jsonify(state)


@app.route('/api/place', methods=['POST'])
def place_building():
    """Apply one building placement, then return the updated game state."""
    global current_game
    if not current_game:
        return jsonify({'error': 'No game in progress'}), 400
    if _is_limited_mode(current_game.mode) and _limited_mode_game_over(current_game):
        return jsonify({'error': 'Game is already over'}), 400

    data = request.get_json(force=True)
    try:
        row = int(data['row'])
        col = int(data['col'])
        building = data['building']
    except (KeyError, TypeError, ValueError):
        return jsonify({'error': 'Invalid placement request'}), 400

    board = current_game.board
    rows = len(board)
    cols = len(board[0])

    if not (0 <= row < rows and 0 <= col < cols):
        return jsonify({'error': 'Out of bounds'}), 400
    if board[row][col]:
        return jsonify({'error': 'Cell already occupied'}), 400
    if building not in ALL_TYPES:
        return jsonify({'error': 'Unknown building type'}), 400

    is_first = current_game.buildings_count == 0
    valid = get_valid_cells(board, is_first, current_game.mode)
    if [row, col] not in valid:
        return jsonify({'error': 'Invalid placement location'}), 400

    # Arcade/Challenge only allow the two offered buildings and charge coins.
    if _is_limited_mode(current_game.mode):
        if building not in current_game.offered_buildings:
            return jsonify({'error': 'Building not offered this turn'}), 400
        placement_cost = get_placement_cost(current_game)
        if current_game.coins < placement_cost:
            return jsonify({'error': f'Not enough coins. This building costs {placement_cost} coins.'}), 400
        current_game.coins -= placement_cost

    board[row][col] = building
    current_game.buildings_count += 1

    # Free Play recalculates economy differently and may expand the board.
    if current_game.mode == FREEPLAY_MODE:
        # Dylan: placing on the border in Free Play can grow the grid so the
        # city gets more buildable space without restarting the run.
        if is_border_cell(board, row, col) and current_game.expansion_count < 2:
            current_game.board = expand_board(board)
            board = current_game.board
            current_game.grid_size = len(board)
            current_game.expansion_count += 1

        # Dylan: profit/upkeep are recomputed every turn, and the consecutive
        # loss counter only rises when upkeep is greater than profit.
        profit, upkeep = freeplay_economy(board)
        current_game.profit = profit
        current_game.upkeep = upkeep
        current_game.loss_turns = current_game.loss_turns + 1 if profit - upkeep < 0 else 0
    else:
        # Limited modes earn/spend coins every turn and refresh offered buildings.
        base_income = arcade_coin_income(board)
        earned_income = apply_income_modifier(current_game, base_income, current_game.turn)
        maintenance_charge = calculate_maintenance_charge(current_game, board, current_game.turn)
        current_game.coins = max(0, current_game.coins + earned_income - maintenance_charge)
        current_game.offered_buildings = random.sample(ALL_TYPES, 2)

        if current_game.mode == CHALLENGE_MODE:
            current_game.challenge_income = earned_income
            current_game.challenge_upkeep = maintenance_charge

    add_board_score_earned(current_game)
    completed_turn = current_game.turn
    current_game.turn += 1

    # --- NEW: Run events and challenges check ---
    notifications = check_events_and_challenges(current_game)
    
    # --- NEW: Stack the persistent bonus score on top of the physical board score ---
    current_game.score += getattr(current_game, 'bonus_score', 0)
    current_game.bonus_score = 0  #Without that reset, bonus_score is a silently-growing snowball that gets re-applied to score on every single placement forever
    # --------------------------------------------

    state = current_game.to_dict()
    
    # Inject notifications into the state
    state['notifications'] = notifications
    
    event_notifications = []
    if current_game.mode == CHALLENGE_MODE:
        event_notifications = process_challenge_turn(current_game, completed_turn)

    # Disasters may have changed the board after the normal turn calculations.
    recalculate_after_destruction(current_game)
    milestone_notifications = check_milestone_challenges(current_game)
    _refresh_challenge_economy(current_game)

    state = _state_response(current_game, event_notifications, milestone_notifications)
    if current_game.mode == FREEPLAY_MODE:
        # Dylan: Free Play ends automatically after 20 loss-making turns in a row.
        game_over = current_game.loss_turns >= 20
    else:
        game_over = _limited_mode_game_over(current_game)

    state['game_over'] = game_over
    if not game_over:
        state['valid_cells'] = get_valid_cells(
            current_game.board,
            current_game.buildings_count == 0,
            current_game.mode,
        )
    else:
        state['valid_cells'] = []
        state['game_over_reason'] = _game_over_reason(current_game)
        state['qualifies'] = _qualifies(current_game.score, current_game.mode)
    return jsonify(state)


@app.route('/api/demolish', methods=['POST'])
def demolish():
    """Remove an existing building and recalculate the affected game state."""
    global current_game
    if not current_game:
        return jsonify({'error': 'No game in progress'}), 400

    data = request.get_json(force=True)
    try:
        row = int(data['row'])
        col = int(data['col'])
    except (KeyError, TypeError, ValueError):
        return jsonify({'error': 'Invalid demolition request'}), 400

    board = current_game.board
    rows = len(board)
    cols = len(board[0])
    if not (0 <= row < rows and 0 <= col < cols):
        return jsonify({'error': 'Out of bounds'}), 400
    if not board[row][col]:
        return jsonify({'error': 'No building at this cell'}), 400

    # Kyston: in Arcade and Challenge, demolition always spends 1 coin so
    # players can trade money for space to rebuild their city layout.
    # Demolition costs 1 coin in the limited modes.
    if _is_limited_mode(current_game.mode):
        if current_game.coins < 1:
            return jsonify({'error': 'Not enough coins to demolish'}), 400
        current_game.coins -= 1

    board[row][col] = None
    # Kyston: after removing a building, the board score/economy is
    # recalculated so the freed space immediately affects the game state.
    recalculate_after_destruction(current_game)

    if current_game.mode == FREEPLAY_MODE:
        profit, upkeep = freeplay_economy(board)
        current_game.profit = profit
        current_game.upkeep = upkeep
        game_over = False
    else:
        game_over = _limited_mode_game_over(current_game)
        _refresh_challenge_economy(current_game)

    state = _state_response(current_game)
    state['game_over'] = game_over
    if not game_over:
        state['valid_cells'] = get_valid_cells(
            board,
            current_game.buildings_count == 0,
            current_game.mode,
        )
    else:
        state['valid_cells'] = []
        state['game_over_reason'] = _game_over_reason(current_game)
        state['qualifies'] = _qualifies(current_game.score, current_game.mode)
    return jsonify(state)


@app.route('/api/save', methods=['POST'])
def save_game():
    """Save the current run into the logged-in player's personal save folder."""
    if not current_game:
        return jsonify({'error': 'No game in progress'}), 400

    current_user = _get_current_user()
    if not current_user:
        return jsonify({'error': 'No account is logged in'}), 400

    # Saves are scoped per account username so one player can never see or
    # overwrite another player's save files.
    player_dir = _player_dir(current_user.get('username'))
    if not player_dir:
        return jsonify({'error': 'Missing or invalid account username'}), 400

    data = request.get_json(force=True)

    raw = data.get('filename', 'save').strip()
    filename = _sanitize(raw) or 'save'

    # Theresa: save the full current game state to disk so the player can
    # come back later and continue the same city from this exact point.
    path = os.path.join(player_dir, f'{filename}.json')
    with open(path, 'w') as f:
        json.dump(current_game.to_dict(), f, indent=2)

    return jsonify({'success': True, 'filename': filename})


@app.route('/api/saves', methods=['GET'])
def list_saves():
    """List only the save files belonging to the current account."""
    current_user = _get_current_user()
    if not current_user:
        return jsonify({'saves': []})

    # Only ever list the requesting player's own saves.
    player_dir = _player_dir(current_user.get('username'), create=False)
    if not player_dir or not os.path.exists(player_dir):
        return jsonify({'saves': []})

    saves = []
    for entry in sorted(os.listdir(player_dir)):
        if not entry.endswith('.json'):
            continue

        filename = entry[:-5]
        path = os.path.join(player_dir, entry)
        mode = 'unknown'

        try:
            with open(path, 'r', encoding='utf-8') as save_file:
                save_data = json.load(save_file)
            raw_mode = str(save_data.get('mode', '')).strip().lower()
            if raw_mode:
                mode = raw_mode
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            app.logger.warning('Could not inspect save %s: %s', filename, error)

        saves.append({'filename': filename, 'mode': mode})

    return jsonify({'saves': saves})


@app.route('/api/save', methods=['DELETE'])
def delete_save():
    """Delete one save file from the current player's save folder."""
    current_user = _get_current_user()
    if not current_user:
        return jsonify({'error': 'No account is logged in'}), 400

    data = request.get_json(force=True)
    player_dir = _player_dir(current_user.get('username'), create=False)
    if not player_dir or not os.path.exists(player_dir):
        return jsonify({'error': 'No save folder found for this account'}), 404

    filename = _sanitize(data.get('filename', ''))
    if not filename:
        return jsonify({'error': 'Missing save filename'}), 400

    path = os.path.join(player_dir, f'{filename}.json')
    if not os.path.exists(path):
        return jsonify({'error': 'Save file not found'}), 404

    try:
        os.remove(path)
    except OSError as error:
        app.logger.warning('Could not delete save %s: %s', filename, error)
        return jsonify({'error': 'Could not delete this save right now.'}), 500

    return jsonify({'success': True, 'filename': filename})


@app.route('/api/load', methods=['POST'])
def load_game():
    """Load one of the logged-in user's save files into memory."""
    global current_game
    current_user = _get_current_user()
    if not current_user:
        return jsonify({'error': 'No account is logged in'}), 400

    data = request.get_json(force=True)
    player_dir = _player_dir(current_user.get('username'), create=False)
    if not player_dir:
        return jsonify({'error': 'Missing or invalid account username'}), 400

    filename = _sanitize(data.get('filename', ''))
    path = os.path.join(player_dir, f'{filename}.json')
    if not os.path.exists(path):
        return jsonify({'error': 'Save file not found'}), 404

    try:
        # Theresa: rebuild the in-memory game from the selected save file so
        # the player resumes from where they last left off.
        with open(path, 'r', encoding='utf-8') as file:
            saved_data = json.load(file)
        current_game = GameState.from_dict(saved_data)
    except (json.JSONDecodeError, OSError, TypeError, ValueError) as error:
        app.logger.warning('Could not load save %s: %s', filename, error)
        return jsonify({'error': 'This save file is invalid or damaged.'}), 400

    state = _state_response(current_game)
    is_first = current_game.buildings_count == 0
    state['valid_cells'] = get_valid_cells(current_game.board, is_first, current_game.mode)
    return jsonify(state)


@app.route('/api/highscores', methods=['GET'])
def get_highscores():
    """Return the global Top 10 data enriched with current avatar metadata."""
    by_id, by_username = _user_index()
    scores = [_with_avatar(score, by_id, by_username) for score in _load_hs()]
    return jsonify({'scores': scores})


@app.route('/api/my_scores', methods=['GET'])
def get_my_scores():
    """Return the requesting player's full recorded score history."""
    history = _load_history()
    current_user = _get_current_user()

    if current_user:
        mine = [s for s in history if _score_matches_user(s, current_user)]
    else:
        name = request.args.get('name', '').strip()
        mine = [s for s in history if str(s.get('name', '')).strip().lower() == name.lower()]

    mine.sort(key=lambda s: s['score'], reverse=True)
    by_id, by_username = _user_index()
    scores = [_with_avatar(score, by_id, by_username) for score in mine]
    return jsonify({'scores': scores})


@app.route('/api/statistics', methods=['GET'])
def get_statistics():
    """Feed the live dashboard widget shown beside the board."""
    if not current_game:
        return jsonify({'error': 'No game in progress'}), 400
    # Dylan: this endpoint powers the in-game dashboard with fresh live stats.
    stats = generate_dashboard_stats(current_game)
    return jsonify(stats)


@app.route('/api/submit_score', methods=['POST'])
def submit_score():
    """Persist the finished run to history and possibly to the Top 10 board."""
    if not current_game:
        return jsonify({'error': 'No game in progress'}), 400

    current_user = _get_current_user()
    if not current_user:
        return jsonify({'error': 'No account is logged in'}), 400

    # Theresa: submitting after game over or early exit keeps the final
    # result and checks whether it should appear on the global Top 10 board.
    made_leaderboard, rank = _add_hs(current_user, current_game.score, current_game.mode, current_game.turn)
    _add_history(current_user, current_game.score, current_game.mode, current_game.turn)
    return jsonify({'success': True, 'made_leaderboard': made_leaderboard, 'rank': rank})

@app.route('/api/end_game_early', methods=['POST'])
def end_game_early():
    """Build the early-exit summary shown before the player returns to menu."""
    global current_game
    if not current_game:
        return jsonify({'error': 'No active game found.'}), 400

    # Calculate final stats for the summary screen
    rows = len(current_game.board)
    cols = len(current_game.board[0])
        
    # FIX: Explicitly ignore None, empty strings, and spaces
    total_buildings = sum(1 for r in range(rows) for c in range(cols) if current_game.board[r][c] not in [None, '', ' '])

    summary_text = f"You survived {current_game.turn} turns and constructed {total_buildings} buildings."

    # Theresa: keep the current run alive long enough for the player to
    # choose whether to save the final score before returning to the menu.
    # Return the data without fully wiping the game state yet, 
    # so the leaderboard submission route still has access to the final score.
    return jsonify({
        'success': True,
        'score': current_game.score,
        'summary': summary_text,
        'game_over_reason': summary_text,
        'mode': current_game.mode
    })

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
