def _adjacent_buildings(board, row, col):
    rows = len(board)
    cols = len(board[0])
    result = []
    for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        nr, nc = row + dr, col + dc
        if 0 <= nr < rows and 0 <= nc < cols and board[nr][nc]:
            result.append(board[nr][nc])
    return result


def score_cell(board, row, col):
    cell = board[row][col]
    if not cell:
        return 0

    rows = len(board)
    cols = len(board[0])
    adj = _adjacent_buildings(board, row, col)

    if cell == 'R':
        # Kyston: Residential scoring depends on nearby buildings so city
        # planning matters: any adjacent Industry forces 1 point, otherwise
        # adjacent Residential/Commercial add 1 each and adjacent Parks add 2.
        if 'I' in adj:
            return 1
        pts = 0
        for n in adj:
            if n in ('R', 'C'):
                pts += 1
            elif n == 'O':
                pts += 2
        return pts

    elif cell == 'I':
        return sum(1 for r in range(rows) for c in range(cols) if board[r][c] == 'I')

    elif cell == 'C':
        return sum(1 for n in adj if n == 'C')

    elif cell == 'O':
        return sum(1 for n in adj if n == 'O')

    elif cell == '*':
        row_data = board[row]
        count = 1
        c = col - 1
        while c >= 0 and row_data[c] == '*':
            count += 1
            c -= 1
        c = col + 1
        while c < cols and row_data[c] == '*':
            count += 1
            c += 1
        return count

    return 0


def compute_total_score(board):
    return sum(
        score_cell(board, r, c)
        for r in range(len(board))
        for c in range(len(board[0]))
        if board[r][c]
    )
