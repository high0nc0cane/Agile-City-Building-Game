def generate_dashboard_stats(game_state):
    """Calculate live statistics from the current game state."""
    if not game_state:
        return {}

    # Dylan: the live dashboard is built from the current board state so the
    # player can monitor city growth and make strategy decisions while playing.
    board = game_state.board
    rows = len(board)
    cols = len(board[0])

    building_counts = {'R': 0, 'I': 0, 'C': 0, 'O': 0, '*': 0}
    total_buildings = 0

    for row in range(rows):
        for col in range(cols):
            cell = board[row][col]
            if cell in building_counts:
                building_counts[cell] += 1
                total_buildings += 1

    stats = {
        'mode': game_state.mode,
        'total_buildings': total_buildings,
        'building_breakdown': building_counts,
        'grid_size': f'{rows}x{cols}',
        'current_turn': game_state.turn,
        'current_score': game_state.score,
    }

    if game_state.mode == 'freeplay':
        stats['net_profit'] = game_state.profit - game_state.upkeep
        stats['consecutive_losses'] = game_state.loss_turns
    elif game_state.mode == 'challenge':
        challenge_state = getattr(game_state, 'challenge_state', {})
        stats['challenge_income'] = getattr(game_state, 'challenge_income', 0)
        stats['challenge_upkeep'] = getattr(game_state, 'challenge_upkeep', 0)
        stats['upcoming_events'] = len(challenge_state.get('pending_events', []))
        stats['active_effects'] = len(challenge_state.get('active_effects', []))

    return stats
