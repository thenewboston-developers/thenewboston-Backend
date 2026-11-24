# Project setup

**SECTIONS**
1. [Initial Project Setup](#initial-project-setup)
2. [Essential Developer Guidelines](#essential-developer-guidelines)


# Initial Project Setup

1. Install Python version 3.10.13 and make sure it is being used in the following steps and later during development
   (it is recommended to use [pyenv](https://github.com/pyenv/pyenv) for Python versions management)

2. Install Poetry

```bash
export PIP_REQUIRED_VERSION=24.2
pip install pip==${PIP_REQUIRED_VERSION} && \
pip install virtualenvwrapper && \
pip install poetry==2.1.3 && \
poetry config virtualenvs.path ${HOME}/.virtualenvs && \
poetry run pip install pip==${PIP_REQUIRED_VERSION}
```

3. Clone the Repository

```bash
git clone https://github.com/thenewboston-developers/thenewboston-Backend.git
```

4. Copy the settings templates into a new local directory:

```bash
mkdir -p local
cp thenewboston/project/settings/templates/settings.dev.py ./local/settings.dev.py
cp thenewboston/project/settings/templates/settings.unittests.py ./local/settings.unittests.py
```

5. Install / upgrade docker as described at https://docs.docker.com/engine/install/
```bash
# Known working versions described in the comments below

docker --version # Docker version 26.0.1, build d260a54

# (!!!) At least Docker Compose version v2.24.0 is required
docker compose version # Docker Compose version v2.26.1
```

6. Commands for setting up local environment. Run the following commands:

```bash
make run-dependencies  # Sets up the necessary Docker containers for Redis and PostgreSQL
make update            # Installs project dependencies, pre-commit and applies database migrations
```

7. Fire Up the Server 🚀

```bash
make run-server       # Starts the Django development server
```

8. Create a superuser and configure the initial data

```bash
make superuser        # Creates a Django superuser account
```

After creating the superuser, you need to set up some initial data:

1. Go to Django admin at http://localhost:8000/admin/
2. Log in with your superuser credentials
3. Navigate to **Currencies** and manually add a currency with the ticker **TNB**
4. Navigate to **Invitation limits** and manually set an invitation limit for your superuser

Now you're all set! The backend is up and ready for action.


# Essential Developer Guidelines

To contribute effectively, follow these guidelines:

- Branch off (new branch) from `master` for new features or fixes.
- Do your work and run `make lint` to ensure code quality.
- Open a Pull Request (PR) for review.
- Wait for approval before merging to `master`. No direct pushes, please!

# Backgammon

Backgammon supports free computer practice and human challenges, with optional TNB stakes for human matches. Matches are played to 1, 3, or 5 points. Singles, gammons, backgammons, doubling-cube ownership, and the Crawford game determine the point score. The TNB stake is fixed for the entire match: cube decisions never increase the coin commitment. Computer games cannot carry a stake.

The server owns dice rolls, legal turns, match clocks, and settlement. A complete turn must use the maximum number of playable dice, including the larger die when only one can be played. Actions include an `expected_version` so stale requests cannot replay moves or payments. Stake, refund, and payout entries are recorded in the match ledger. Free games do not require a wallet.

The API is under `/api/backgammon/matches`. Creation requires a UUID `request_id` that is reused for retries, and selects `mode`, `opponent_id` for human games, `difficulty`, `stake_amount`, `target_score`, and `time_limit_seconds`. Pending matches are invitations; their actions are `accept`, `decline`, and `cancel`. Active match actions are `roll`, `move`, `double`, `respond-double`, `next-game`, and `resign`. A finished match can create a `rematch`. The detail response includes available complete turns for the player currently moving. Public match state supports spectating; pending invitations are private to their participants.

The computer is a local heuristic opponent, not GNU Backgammon or a tournament-strength engine. Easy chooses legal outcomes randomly, normal evaluates board position, and hard considers sampled replies. Computer turns run through Celery. Run both the worker and Beat scheduler alongside the API; the scheduler also handles abandoned challenges and match clocks. New database tables are installed by the normal deployment migration step.

Run the game tests with `poetry run pytest thenewboston/backgammon/tests`. Tests require the same PostgreSQL and Redis services as the rest of the backend suite.

# Reversi

Reversi (Othello) supports free computer practice, including guest play without an account, and human challenges with optional TNB stakes. Black moves first. The creator picks `color` (`black`, `white`, or `random`, decided by the server), and the opponent sees the colors before accepting. A rematch between two members swaps colors. Computer games cannot carry a stake.

The server owns the board, legal moves, clocks, and settlement. A move must outflank at least one opposing disk. A player without a legal move passes automatically; the game ends when neither player can move, and the side with more disks wins. Both stakes form the prize: the winner receives the whole pool with no fee, and a draw returns each stake. Resigning or running out of time loses the match. Actions include an `expected_version` so stale requests cannot replay moves or payments. Stake, refund, and payout entries are recorded in the match ledger. Free games do not require a wallet.

The API is under `/api/reversi/matches`. Creation requires a UUID `request_id` that is reused for retries, and selects `mode`, `opponent_id` for human games, `difficulty`, `color`, `stake_amount`, and `time_limit_seconds` (300, 600, 900, or 1800 per player for the whole match). Pending matches are invitations that expire after five minutes; their actions are `accept`, `decline`, and `cancel`. Active match actions are `move` (`row` and `column`, zero-based from the top-left) and `resign`. A finished match can create a `rematch`. The detail response includes `legal_moves` for the side to move and `last_move` with the flipped disks. Reversi has no hidden information, so a member's started match can be watched by anyone. Invitations that are pending or never started are private to their participants, and guest games are private to their guest session (`X-Guest-Token`, see `DEPLOY.md`).

The computer is a local opponent. Easy plays a random legal move, normal picks the best position one move ahead, and hard searches four moves ahead and plays the last eight squares exactly. Computer turns run through Celery, and the search runs before the match row is locked. Run both the worker and Beat scheduler alongside the API; the scheduler also expires challenges, flags fallen clocks, and retries missed computer turns. New database tables are installed by the normal deployment migration step.

Run the game tests with `poetry run pytest thenewboston/reversi/tests`.

# Mancala

Mancala is the Kalah game: six pits a side with four stones each. A move sows one pit counter-clockwise, one stone per pit, through the mover's own store and past the opponent's. A last stone in the mover's store earns another turn. A last stone in an empty pit on the mover's side captures it together with the stones opposite, if there are any. When one row is empty the stones left in the other row go to that row's owner, and the fuller store wins. Equal stores are a draw.

The API is under `/api/mancala/matches` and follows the Backgammon and Battleship conventions: creation takes a UUID `request_id` (reuse it when retrying), `mode`, `opponent_id` for human games, `difficulty`, `stake_amount`, and `time_limit_seconds` (300, 600, 900, or 1800). Pending matches are invitations with `accept`, `decline`, and `cancel`. Active matches take `move` with `pit` (0-5, counted in sowing order, so 5 is next to the mover's store) and `resign`; a finished match can create a `rematch`. Every action carries `expected_version`. The side that moves first is chosen at random when the game starts.

`board` is a list of 14 counts in sowing order: indexes 0-5 are the host's pits, 6 the host's store, 7-12 the guest's pits, and 13 the guest's store. The detail response also carries `recent_moves`, the last eight moves with the board after each one, so a client can show every pit the computer played between two polls. Boards are public and started matches can be watched; pending invitations are visible only to their two players.

Human matches can carry equal, fixed TNB stakes. The challenger's stake is locked when the challenge is sent and the opponent's when it is accepted. The winner receives both; a draw refunds both; a cancelled, declined, or expired challenge refunds the challenger. Each player has one clock for the whole match that runs only on their turns. Running out of time or resigning loses the match. Stakes, refunds, and payouts are recorded in the match ledger.

Computer games are free. Signed-out visitors can play them too, with the guest session described in `DEPLOY.md` (`X-Guest-Token`): a guest game is private to its session, cannot carry a stake, and a win only previews the reward an account would have earned. Easy plays any legal pit, normal looks two moves ahead, and hard searches deeper within a fixed budget of positions. Computer turns run through Celery, one pit per task, and the 15-second sweep also settles expired challenges and clocks and retries computer turns that were not delivered. Keep the worker and Beat running.

Run the game tests with `poetry run pytest thenewboston/mancala/tests`.

# Dots and Boxes

Dots and Boxes supports free computer practice, including guest play without an account, and human challenges with optional TNB stakes. The board is 3, 4, or 5 boxes a side (`board_size`). Players take turns drawing one line between two neighbouring dots. Drawing the fourth side of a box claims it and keeps the turn, so one turn can be several lines. The game ends when every box is claimed; the player with more boxes wins, and equal boxes (possible on the 4 by 4 board) is a draw.

The server owns the board, clocks, and settlement. Blue is the player who created the match and draws first; red is the invited member or the computer. Both stakes form the prize: the winner receives the whole pool with no fee, and a draw returns each stake. A cancelled, declined, or expired challenge refunds the challenger. Each player has one clock for the whole match that runs on their turns, including while they keep the turn. Resigning or running out of time loses the match. Stake, refund, and payout entries are recorded in the match ledger. Free games do not require a wallet, and computer games cannot carry a stake.

The API is under `/api/dots-and-boxes/matches`. Creation requires a UUID `request_id` that is reused for retries, and selects `mode`, `opponent_id` for human games, `difficulty`, `board_size`, `stake_amount`, and `time_limit_seconds` (300, 600, 900, or 1800). Pending matches are invitations that expire after five minutes; their actions are `accept`, `decline`, and `cancel`. Active match actions are `move` (one `line` number per request) and `resign`. A finished match can create a `rematch`, which the player who asks for it opens as blue. Every action carries `expected_version`.

Lines are numbered row by row: first the horizontal lines from the top edge down, then the vertical lines, left to right within each row of boxes (`rules.py` has the exact layout). `lines` and `boxes` hold 0 for open, 1 for blue, and 2 for red. `moves` lists the line numbers in the order they were drawn, so a client can replay the lines drawn between two polls. A member's started match can be watched by anyone. Pending invitations are private to their participants, and guest games are private to their guest session (`X-Guest-Token`, see `DEPLOY.md`).

The computer is a local opponent. Easy takes any box on offer and otherwise draws at random. Normal also avoids giving boxes away while it can, then gives away as few as possible. Hard adds chain control (it may leave the last two boxes of a chain to make the opponent open the next one) and solves the position exactly once it is small enough, within a fixed budget. Computer turns run through Celery: the whole turn is planned before the match row is locked and commits at once. Run both the worker and Beat scheduler alongside the API; the scheduler also expires challenges, flags fallen clocks, and retries missed computer turns. New database tables are installed by the normal deployment migration step.

Run the game tests with `poetry run pytest thenewboston/dots_and_boxes/tests`.

# Hex

Hex is played on a rhombus of hexagonal cells, 7, 9, 11 (the default), or 13 to a side. Red moves first and wins by joining the top and bottom edges with an unbroken chain of red stones; Blue wins by joining the left and right edges. Players take turns placing one stone on any empty cell, and stones never move or come off. A game cannot be drawn: a full board always holds exactly one winning chain.

Moving first is a large advantage, so matches between two players use the swap rule: as the reply to Red's first stone, and only then, Blue may take that stone over instead of placing one. The stone turns blue and moves to its mirror cell (row and column exchanged), the players keep their colours and edges, and Red moves next. Computer games have no swap: the player is Red and keeps the opening.

The API is under `/api/hex/matches` and follows the Checkers conventions: creation takes a UUID `request_id` (reuse it when retrying), `mode`, `opponent_id` for human games, `difficulty`, `stake_amount`, `time_limit_seconds` (300, 600, 900, or 1800), and `board_size`. Pending matches are invitations with `accept`, `decline`, and `cancel`. Active matches take `move` with `cell`, `swap`, and `resign`; a finished match can create a `rematch`, in which the player who asks moves first. Every action carries `expected_version`.

`board` lists the cells row by row (`cell = row * board_size + column`) as 0 for empty, 1 for red, and 2 for blue. A cell touches its row neighbours, the cells above it in the same and the next column, and the cells below it in the previous and the same column. The detail response adds `can_swap` for the player who may swap right now, `last_move`, and, once a side has connected, `winning_path`: the shortest chain of that side's stones between its edges. Started matches are public and can be watched; pending invitations are visible only to their two players.

Human matches can carry equal, fixed TNB stakes. The challenger's stake is locked when the challenge is sent and the opponent's when it is accepted. The winner receives both, and a cancelled, declined, or expired challenge refunds the challenger. Each player has one clock for the whole match that runs only on their turns. Running out of time or resigning loses the match. Stakes, refunds, and payouts are recorded in the match ledger.

Computer games are free, and signed-out visitors can play them with the guest session described in `DEPLOY.md`. A signed-in player who completes a connection against the computer earns the 10 TNB community fund reward described below, at any difficulty; timeouts and resignations earn nothing. The computer scores positions by two-distance, the evaluation classic Hex programs use: easy plays a random cell on either side's shortest path, normal picks among the moves that score best, and hard searches three moves deep. Computer turns run through Celery, and the 10-second sweep also settles expired challenges and clocks and retries computer turns that were not delivered. Keep the worker and Beat running.

Run the game tests with `poetry run pytest thenewboston/hex/tests`.

# Computer games and the community game fund

Connect Five now supports private computer matches at easy, normal, and hard difficulty. Create one with `POST /api/connect-five/matches/computer`, a UUID `request_id`, `difficulty`, and `time_limit_seconds` (300, 600, 900, or 1800). Reuse the request ID after a network failure. Both sides start with two of each special; computer matches have no stakes, paid purchases, or ranked statistics. Moves and resignations require `expected_version`. The detail response includes `active_side`, `winner_side`, `version`, and `server_time`; the frontend polls private computer matches. Celery runs computer turns and the existing timeout sweep retries missed work. Keep both the worker and Beat running.

The shared TNB fund pays **10 TNB for a completed computer-match win** in Connect Five, Backgammon, Battleship, Reversi, Mancala, Dots and Boxes, or Hex, at any difficulty. Connect Five requires five connected pieces; Battleship requires sinking the fleet; Backgammon requires winning the whole match (including a computer declining a double); Reversi requires finishing the game with more disks; Mancala requires finishing the game with the fuller store; Dots and Boxes requires claiming more boxes on a completed board; Hex requires joining both of the player's edges. Timeouts, resignations, draws, partial Backgammon rounds, and human matches do not earn fund rewards. Human stakes continue to use their existing settlement paths.

`GET /api/game-fund` publicly reports the balance, reward amount, funded wins, deposited/paid totals, and availability. Authenticated players contribute from their TNB wallet with `POST /api/game-fund/deposits` and `{amount, request_id}`. Amounts must be whole TNB from 1 through 1,000,000,000. Contributions are final and cannot be withdrawn. Reusing a donor's request ID with the same amount returns the original receipt; changing the amount returns 409.

The pool starts empty. Rewards are not reserved when a match starts: the fund must be enabled and hold at least 10 TNB when the win completes. Otherwise the player earns nothing, free play continues, and later contributions never replay earlier wins. Every completed computer match records `computer_reward` as `paid`, `fund_empty`, or `not_eligible`; active and historical matches can have a null receipt. No client-facing reward-claim endpoint exists.

Fund decisions, game completion, and wallet changes share a database transaction. Row locks serialize fund spending, unique ledger constraints prevent duplicate deposits or rewards, and database constraints enforce `total_deposited = balance + total_paid`. Django admin exposes read-only ledgers and an `enabled` pause control. Run the normal migrations before starting updated workers; no initial funding or extra infrastructure is required.

Run `poetry run pytest thenewboston/connect_five/tests thenewboston/game_rewards/tests thenewboston/wallets/tests` for computer gameplay, reward integration, and concurrent wallet/fund checks.
