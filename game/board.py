def get_valid_cells(board, is_first_turn, mode='arcade'):
    rows = len(board)
    cols = len(board[0])

    if mode == 'freeplay':
        return [[r, c] for r in range(rows) for c in range(cols) if not board[r][c]]

    if is_first_turn:
        return [[r, c] for r in range(rows) for c in range(cols) if not board[r][c]]

    valid = set()
    for r in range(rows):
        for c in range(cols):
            if board[r][c]:
                for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < rows and 0 <= nc < cols and not board[nr][nc]:
                        valid.add((nr, nc))
    return [[r, c] for r, c in valid]


def is_border_cell(board, row, col):
    rows = len(board)
    cols = len(board[0])
    return row == 0 or row == rows - 1 or col == 0 or col == cols - 1


def expand_board(board):
    # Dylan: Free Play expands by adding space around the existing city when
    # the player builds on an outer edge, letting the run continue on a larger grid.
    """Add 5 rows/cols to each side of the board."""
    old_rows = len(board)
    old_cols = len(board[0])
    new_rows = old_rows + 10
    new_cols = old_cols + 10

    new_board = [[None] * new_cols for _ in range(new_rows)]
    for r in range(old_rows):
        for c in range(old_cols):
            new_board[r + 5][c + 5] = board[r][c]

    return new_board
