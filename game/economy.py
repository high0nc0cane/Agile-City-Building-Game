def arcade_coin_income(board):
    """Coins generated each turn from Industry and Commercial buildings adjacent to Residential."""
    rows = len(board)
    cols = len(board[0])
    coins = 0
    for r in range(rows):
        for c in range(cols):
            if board[r][c] in ('I', 'C'):
                for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < rows and 0 <= nc < cols and board[nr][nc] == 'R':
                        coins += 1
    return coins


def freeplay_economy(board):
    """Returns (profit, upkeep) for the current board state in Free Play mode."""
    rows = len(board)
    cols = len(board[0])
    profit = 0
    upkeep = 0

    # Dylan: each Free Play turn totals profit and upkeep from the whole
    # board so the player can see their current financial standing.
    for r in range(rows):
        for c in range(cols):
            cell = board[r][c]
            if cell == 'R':
                profit += 1
            elif cell == 'I':
                profit += 2
                upkeep += 1
            elif cell == 'C':
                profit += 3
                upkeep += 2
            elif cell == 'O':
                upkeep += 1
            elif cell == '*':
                left = c > 0 and board[r][c - 1] == '*'
                right = c < cols - 1 and board[r][c + 1] == '*'
                if not left and not right:
                    upkeep += 1

    # Dylan: Residential upkeep is charged per connected cluster rather than
    # per tile, which affects how players plan housing layouts in Free Play.
    # Residential cluster upkeep: each cluster costs 1 coin/turn
    visited = [[False] * cols for _ in range(rows)]
    for sr in range(rows):
        for sc in range(cols):
            if board[sr][sc] == 'R' and not visited[sr][sc]:
                queue = [(sr, sc)]
                visited[sr][sc] = True
                while queue:
                    cr, cc = queue.pop(0)
                    for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                        nr, nc = cr + dr, cc + dc
                        if (0 <= nr < rows and 0 <= nc < cols
                                and board[nr][nc] == 'R'
                                and not visited[nr][nc]):
                            visited[nr][nc] = True
                            queue.append((nr, nc))
                upkeep += 1

    return profit, upkeep
