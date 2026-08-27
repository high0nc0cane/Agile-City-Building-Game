import json
import os
import re


BASE_DIR = os.path.dirname(__file__)
# Theresa: user accounts are stored in users.json so each player's profile
# and scores can be kept separate across logins.
USERS_FILE = os.path.join(BASE_DIR, 'users.json')


DEFAULT_USER = {
    'user_id': 1,
    'username': 'shinchan',
    'password': 'shinchan123',
    'display_name': 'Shinchan',
    'avatar_filename': '',
}


def _is_valid_user_record(user_record):
    if not isinstance(user_record, dict):
        return False

    try:
        user_id = int(user_record.get('user_id'))
        username = str(user_record.get('username', '')).strip()
        password = str(user_record.get('password', ''))
        display_name = str(user_record.get('display_name', '')).strip()
    except (TypeError, ValueError):
        return False

    return bool(user_id > 0 and username and password and display_name)


def _clean_user_record(user_record):
    return {
        'user_id': int(user_record['user_id']),
        'username': str(user_record['username']).strip(),
        'password': str(user_record['password']),
        'display_name': str(user_record['display_name']).strip(),
        'avatar_filename': str(user_record.get('avatar_filename', '')).strip(),
    }


def create_default_users_file():
    users_data = {'users': [DEFAULT_USER.copy()]}
    save_users(users_data)
    return users_data


def load_users():
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as file_handle:
            content = file_handle.read().strip()
    except FileNotFoundError:
        print('users.json was missing. Creating the default account file.')
        return create_default_users_file()
    except OSError as error:
        print(f'Could not read users.json: {error}')
        return {'users': [DEFAULT_USER.copy()]}

    if not content:
        print('users.json was empty. Rebuilding it safely.')
        return create_default_users_file()

    try:
        loaded_data = json.loads(content)
    except json.JSONDecodeError:
        print('users.json contains invalid JSON. Rebuilding it safely.')
        return create_default_users_file()

    users_list = []
    if isinstance(loaded_data, dict):
        raw_users = loaded_data.get('users', [])
        if isinstance(raw_users, list):
            for user_record in raw_users:
                if _is_valid_user_record(user_record):
                    users_list.append(_clean_user_record(user_record))

    if not users_list:
        print('No valid user accounts were found. Creating the default account.')
        return create_default_users_file()

    return {'users': users_list}


def save_users(user_data):
    users_list = []
    if isinstance(user_data, dict):
        raw_users = user_data.get('users', [])
        if isinstance(raw_users, list):
            for user_record in raw_users:
                if _is_valid_user_record(user_record):
                    users_list.append(_clean_user_record(user_record))

    with open(USERS_FILE, 'w', encoding='utf-8') as file_handle:
        json.dump({'users': users_list}, file_handle, indent=4)


def validate_username(username):
    if not isinstance(username, str):
        return False
    return bool(re.fullmatch(r'[A-Za-z0-9_]{3,15}', username))


def username_exists(username, users):
    if not username or not isinstance(users, list):
        return False

    username_lower = username.strip().lower()
    for user_record in users:
        if not isinstance(user_record, dict):
            continue
        existing_username = str(user_record.get('username', '')).strip().lower()
        if existing_username == username_lower:
            return True
    return False


def _next_user_id(users):
    highest_user_id = 0
    for user_record in users:
        if not isinstance(user_record, dict):
            continue
        try:
            highest_user_id = max(highest_user_id, int(user_record.get('user_id', 0)))
        except (TypeError, ValueError):
            continue
    return highest_user_id + 1 if highest_user_id else 1


def create_account(display_name, username, password, confirm_password):
    users_data = load_users()
    users = users_data['users']

    # Theresa: create a brand new player account record with its own
    # nickname, login credentials, and profile slot in users.json.
    # Daphne: display_name is the player-facing nickname shown in the UI,
    # saves, and score records so each player can be identified by name.
    display_name = str(display_name).strip() if display_name is not None else ''
    username = str(username).strip() if username is not None else ''
    password = '' if password is None else str(password)
    confirm_password = '' if confirm_password is None else str(confirm_password)

    if not display_name:
        raise ValueError('Display name cannot be empty.')
    if len(display_name) > 20:
        raise ValueError('Display name must be 20 characters or fewer.')
    if not username:
        raise ValueError('Username cannot be empty.')
    if not validate_username(username):
        raise ValueError('Username must be 3 to 15 characters and use only letters, numbers, or underscores.')
    if username_exists(username, users):
        raise ValueError('That username already exists.')
    if not password:
        raise ValueError('Password cannot be empty.')
    if len(password) < 6:
        raise ValueError('Password must be at least 6 characters long.')
    if password != confirm_password:
        raise ValueError('Passwords do not match.')

    new_user = {
        'user_id': _next_user_id(users),
        'username': username,
        'password': password,
        'display_name': display_name,
        'avatar_filename': '',
    }
    users.append(new_user)
    save_users(users_data)
    return new_user


def login(username, password):
    users_data = load_users()
    users = users_data['users']

    # Theresa: log in by matching the entered credentials to an existing
    # saved account, then return that player's profile data.
    username = str(username).strip() if username is not None else ''
    password = '' if password is None else str(password)

    for user_record in users:
        if not isinstance(user_record, dict):
            continue
        existing_username = str(user_record.get('username', '')).strip()
        existing_password = str(user_record.get('password', ''))
        if existing_username.lower() == username.lower() and existing_password == password:
            return _clean_user_record(user_record)

    raise ValueError('Incorrect username or password.')


def account_menu(action, form_data=None):
    form_data = form_data or {}
    if action == 'login':
        return login(form_data.get('username', ''), form_data.get('password', ''))
    if action == 'create':
        return create_account(
            form_data.get('display_name', ''),
            form_data.get('username', ''),
            form_data.get('password', ''),
            form_data.get('confirm_password', ''),
        )
    if action == 'exit':
        return None
    raise ValueError('Unsupported account action.')


def update_avatar(user_id, avatar_filename):
    users_data = load_users()
    users = users_data['users']

    for user_record in users:
        if not isinstance(user_record, dict):
            continue
        try:
            if int(user_record.get('user_id', 0)) != int(user_id):
                continue
        except (TypeError, ValueError):
            continue

        user_record['avatar_filename'] = str(avatar_filename or '').strip()
        save_users(users_data)
        return _clean_user_record(user_record)

    raise ValueError('User account not found.')
