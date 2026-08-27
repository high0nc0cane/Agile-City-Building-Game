# Ngee Ann City

A city-building strategy game built with Flask and a browser UI. Place buildings on a grid, score points using adjacency rules, and compete for the top 10 leaderboard.

## Features

*   **Three Game Modes:** Arcade (resource-limited), Free Play (economy-driven), and Challenge Mode (events & disasters).
*   **User Accounts:** Secure registration and login system with customizable profile pictures.
*   **Persistent Data:** User-specific isolated save files, personal score history, and global mode-based highscores.
*   **Live Statistics:** Real-time dashboard tracking city economy, building breakdowns, and active modifiers.
*   **Responsive UI:** Fully responsive frontend built with HTML/CSS/JS.

## Game Modes

### Arcade
*   Start with 16 coins on a 20x20 grid.
*   Each turn you must choose 1 of 2 random building types to place.
*   First turn can be placed anywhere; subsequent turns must be adjacent to an existing building.
*   Each placement costs a base of 1 coin. 
*   Game ends when the board is full or coins reach 0.

### Free Play
*   Unlimited coins, starts on a 5x5 grid.
*   Build any building anywhere, at any time.
*   Building on the border expands the board (up to two expansions).
*   Each turn calculates profit and upkeep. Game ends automatically after 20 consecutive loss turns.

### Challenge Mode
*   Includes all Arcade rules, plus dynamic difficulty scaling and random events.
*   **Dynamic Costs:** Base building costs increase by 1 coin every 5 turns.
*   **Milestones:** Earn flat score bonuses by completing challenges like "Urban Planner" (5 Residential) or "Metropolis" (15 Buildings).
*   **Events & Disasters:** 15% chance per turn for economic booms, recessions, grants, tax collections, earthquakes, tornadoes, or fires.

## Scoring Rules

*   **Residential (R):** If adjacent to any Industry, scores 1 total. Otherwise +1 per adjacent Residential or Commercial, +2 per adjacent Park.
*   **Industry (I):** Scores +1 per Industry in the entire city.
*   **Commercial (C):** Scores +1 per adjacent Commercial.
*   **Park (O):** Scores +1 per adjacent Park.
*   **Road (*):** Scores +1 per connected Road in the same row.

## Free Play Economy

*   **Residential:** +1 profit each, plus 1 upkeep per connected Residential cluster.
*   **Industry:** +2 profit, -1 upkeep.
*   **Commercial:** +3 profit, -2 upkeep.
*   **Park:** -1 upkeep.
*   **Road:** Unconnected road segments cost -1 upkeep.

## Getting Started

### Prerequisites
*   Python 3.10+ recommended

### Setup

    pip install -r requirements.txt

### Run

    python app.py

Open the game at: http://localhost:5000

## Project Structure

    app.py                  Flask app and API routes
    account.py              User authentication and account management
    requirements.txt        Python dependencies
    game/                   Game logic (board, scoring, economy, state, events, stats)
    static/                 Frontend JS/CSS
      └── profile_pics/     User uploaded avatars
    templates/              HTML templates
    saves/                  User-specific saved games directories
    users.json              Registered user accounts database
    highscores.json         Persistent global Top 10 scores
    score_history.json      Complete historical log of all finished games
    input/                  Assignment guide and notes
    wireframes/             UI wireframe images
    GOLANG_GUIDE.md         Guide for porting to Go (Gin)

## API Endpoints (Backend)

### Account API
*   `POST /api/account`: Handle login, create account, and exit actions via `{ action, username, password, ... }`
*   `POST /api/account/avatar`: Upload/update the logged-in user's profile picture
*   `GET /api/current_user`: Fetch the currently authenticated session user

### Game State API
*   `POST /api/new_game`: Start a new game with `{ mode: "arcade" | "freeplay" | "challenge" }`
*   `GET /api/state`: Get current game state and valid moves
*   `GET /api/statistics`: Get live dashboard statistics for the active run
*   `POST /api/place`: Place a building at `{ row, col, building }`
*   `POST /api/demolish`: Demolish a building at `{ row, col }`
*   `POST /api/end_game_early`: Forfeit the current run and calculate final summary

### Data Persistence API
*   `POST /api/save`: Save current game to user's folder with `{ filename }`
*   `GET /api/saves`: List saved games belonging to the logged-in user
*   `POST /api/load`: Load a user's saved game with `{ filename }`
*   `DELETE /api/save`: Delete a specific save file via `{ filename }`
*   `GET /api/highscores`: Get enriched global Top 10 leaderboard entries
*   `GET /api/my_scores`: Get complete score history for the authenticated user
*   `POST /api/submit_score`: Submit the current active run to history and leaderboards
