# Connect Five Technical Plan (TNB only)

This plan follows existing thenewboston backend and frontend conventions and aligns with
CONNECT_FIVE_BUSINESS_REQUIREMENTS.md. It is high-level but build-ready.

## 0. Scope and assumptions
- Currency: TNB only (settings.DEFAULT_CURRENCY_TICKER).
- Challenge is directed to a specific opponent (opponent_id). If open challenges are desired, confirm.
- Challenger is Player A and moves first. Confirm if this should be randomized.
- Draw definition: board is full and no connect-5 was created by the last move.
- Special prices are fixed constants (need product values).

## 1. App structure
Create a new Django app at `thenewboston/connect_five` following current project layout:
- `apps.py`, `admin.py`, `__init__.py`
- `constants.py` (board size, connect length, special prices)
- `enums.py` (challenge/match states, move types, event types)
- `models/`
  - `challenge.py`
  - `match.py`
  - `match_player.py` (per-player state and inventory)
  - `match_event.py` (audit log)
  - `escrow.py` (escrow + ledger entries)
  - `idempotency.py`
- `serializers/` (read/write for challenge, match, move, purchase, events)
- `views/` (viewsets + actions for accept, cancel, move, purchase)
- `urls.py` (SimpleRouter + custom actions)
- `consumers/` (optional websocket consumer for match updates)
- `tasks.py` (challenge expiry + timeout sweeper)
- `services/`
  - `rules.py` (move validation + win/draw detection)
  - `clocks.py` (authoritative time calculations)
  - `escrow.py` (wallet transfers + invariants)

Integration points:
- Add `thenewboston.connect_five.apps.ConnectFiveConfig` to `INSTALLED_APPS`
  in `thenewboston/project/settings/base.py`.
- Add routes in `thenewboston/project/urls.py` via `include(connect_five.urls)`.
- Add websocket route in `thenewboston/project/routing.py` if realtime is used.
- Add MessageType values in `thenewboston/general/enums.py` (and frontend
  SocketDataType).
- Add Celery beat schedule in `thenewboston/project/settings/celery.py`
  for challenge expiry and match timeout sweeps.

## 2. State machines

### 2.1 Challenge lifecycle
States: PENDING, ACCEPTED, EXPIRED, CANCELLED
- Create: challenger creates -> PENDING
- Accept: opponent accepts -> ACCEPTED (creates match, terminal for challenge)
- Expire: system job -> EXPIRED (>= 5 minutes from created_date)
- Cancel: challenger cancels -> CANCELLED

Transition rules and actors:
- Only challenger can cancel PENDING challenge.
- Only designated opponent (or any user if open challenges are allowed) can accept.
- System can expire only if still PENDING and now >= expires_at.
- ACCEPTED is terminal; EXPIRED and CANCELLED are terminal.

### 2.2 Match lifecycle
States: ACTIVE, FINISHED_CONNECT5, FINISHED_TIMEOUT, DRAW, CANCELLED
- Create: on challenge acceptance -> ACTIVE
- ACTIVE -> FINISHED_CONNECT5: system after a valid placement creates connect-5
- ACTIVE -> FINISHED_TIMEOUT: system after clock <= 0
- ACTIVE -> DRAW: system after valid move fills board with no winner
- ACTIVE -> CANCELLED: admin/system only (dispute resolution, data repair)

Transition rules and actors:
- Only active player can submit a move.
- Any player can purchase Specials without changing turn.
- Timeout and draw are system-triggered based on authoritative time and board state.

## 3. Money and escrow flow (TNB only)
Use `Wallet` balances with explicit escrow and ledger entries to ensure auditability
and idempotency.

### 3.1 Sequence of funds movement
Create challenge (challenger):
1. Validate TNB wallet exists and balance >= stake.
2. Create challenge in PENDING with expires_at = created_date + 5 minutes.
3. Create escrow record and ledger entry (action=stake_lock).
4. Debit challenger wallet by stake amount (locked funds).

Accept challenge (opponent):
1. Validate challenge PENDING and not expired.
2. Validate opponent wallet balance >= stake.
3. Debit opponent wallet by stake amount.
4. Update escrow contributions and prize_pool_total.
5. Mark challenge ACCEPTED, create match ACTIVE.

Purchase Specials (either player, any time):
1. Validate match ACTIVE.
2. Validate player spent_total + purchase_total <= max_spend.
3. Debit player wallet by purchase_total.
4. Update escrow contributions and prize_pool_total.
5. Increment inventory counts for that player.

Win payout (connect-5 or timeout):
1. Determine winner.
2. Credit winner wallet by prize_pool_total.
3. Mark escrow settled, match finished with reason.

Draw refund:
1. Credit each player by their own contribution (stake + purchases).
2. Mark escrow settled, match DRAW.

Expire/cancel:
- Challenge EXPIRED or CANCELLED refunds challenger stake.
- Match CANCELLED refunds each player contribution (same as draw).

### 3.2 Invariants to enforce
- prize_pool_total == sum(player_a_contrib, player_b_contrib)
- player_spend_total <= max_spend for each player
- inventory counts are never negative
- escrow is settled exactly once (win or draw/cancel)
- all money operations are TNB only

### 3.3 Idempotency for money operations
Use `Idempotency-Key` header for all state-changing endpoints.
Store request hash + response snapshot per user and endpoint:
- If key exists with same request hash, return stored response.
- If key exists with different hash, return 409 Conflict.

Each wallet/escrow operation should also create a unique ledger entry
(unique on action + match/challenge + idempotency_key) to prevent double debits/credits
under retries or concurrent requests.

## 4. Chess-style clocks and timeouts
Authoritative time lives on the server. Store per match:
- active_player_id (or slot)
- clock_a_remaining_ms, clock_b_remaining_ms
- turn_started_at (server timestamp)
- turn_number (monotonic, increments each move)

### 4.1 Time algorithm
On any state-changing request (move or purchase):
1. now = timezone.now()
2. elapsed = now - turn_started_at
3. Subtract elapsed from active player remaining time.
4. If remaining <= 0, finish match with FINISHED_TIMEOUT.
5. If move succeeded and match still ACTIVE:
   - switch active_player
   - set turn_started_at = now
   - increment turn_number
6. If purchase (no turn change), keep active_player, but set turn_started_at = now
   after accounting for elapsed time.

### 4.2 Reliable timeout handling
Backstop sweeper:
- Celery beat task runs every 15-30 seconds.
- Query ACTIVE matches where now - turn_started_at >= active_player_remaining.
- For each, `select_for_update` and re-check:
  - status still ACTIVE
  - turn_number and turn_started_at unchanged
  - remaining time still <= 0 after recompute
- Mark FINISHED_TIMEOUT, settle escrow.

This prevents stale sweeper checks from ending a game after a move already advanced the turn.

## 5. Rules engine specification

### 5.1 Board and coordinates
- 14x14 grid.
- Use 0-based coordinates: x in [0,13], y in [0,13].
- Player A uses value 1, Player B uses value 2, empty is 0.

### 5.2 Move types and validation
SINGLE:
- Place one piece at (x, y) if empty.

H2:
- Place two pieces at (x, y) and (x+1, y).
- Valid only if x in [0,12], both cells in bounds and empty.

V2:
- Place two pieces at (x, y) and (x, y+1).
- Valid only if y in [0,12], both cells in bounds and empty.

CROSS4:
- Use (x, y) as center (center is not filled).
- Place at (x-1, y), (x+1, y), (x, y-1), (x, y+1).
- All four target cells must be in bounds and empty.
- Center cell can be empty or occupied (confirm with product).

BOMB:
- Target (x, y) must contain opponent piece.
- Remove exactly one opponent piece.
- Consumes the turn and the Special.

Invalid move results in no state change and returns validation errors.
Multi-piece placements must be fully valid or fully rejected (no partial placement).

### 5.3 Win detection
- After any placement (SINGLE, H2, V2, CROSS4), check connect-5 immediately.
- Check all four directions (horizontal, vertical, two diagonals) from each newly
  placed piece; if any line length >= 5, match ends.
- Bomb does not trigger win detection (it removes a piece only).

### 5.4 Draw detection
- After a valid placement, if board has no empty cells and no winner, mark DRAW.
- Bomb cannot create a draw because it removes a piece.

## 6. API contract (high level)
All state-changing endpoints require `Idempotency-Key` header.

Challenges:
- POST `/api/connect-five/challenges`
  - Request: `opponent_id`, `stake_amount`, `max_spend_amount`, `time_limit_seconds`
  - Response: challenge summary (id, status, expires_at, stake, max_spend, time_limit)
  - Errors: 400 invalid values, 404 opponent not found, 422 insufficient funds
- GET `/api/connect-five/challenges?status=&mine=`
  - List challenges with pagination
- POST `/api/connect-five/challenges/{id}/accept`
  - Response: match summary
  - Errors: 403 not allowed, 409 already accepted, 410 expired
- POST `/api/connect-five/challenges/{id}/cancel`
  - Response: challenge summary
  - Errors: 403 not challenger, 409 not pending

Matches:
- GET `/api/connect-five/matches/{id}`
  - Response: match snapshot with board, clocks, prize pool, inventories
- GET `/api/connect-five/matches?status=&mine=`
  - List matches with pagination
- POST `/api/connect-five/matches/{id}/move`
  - Request: `move_type`, `x`, `y` (or move-specific fields)
  - Response: match snapshot + move/event id
  - Errors: 400 invalid move, 403 not your turn, 409 match not active, 410 match ended
- POST `/api/connect-five/matches/{id}/purchase`
  - Request: `special_type`, `quantity` (default 1)
  - Response: inventories, remaining spend, updated prize pool
  - Errors: 400 invalid special, 422 max spend exceeded, 409 match not active

Error format should follow existing DRF validation patterns.

## 7. Data models
High-level model outline (names may vary):

ConnectFiveChallenge:
- challenger (FK users.User)
- opponent (FK users.User, nullable)
- stake_amount, max_spend_amount, time_limit_seconds
- status, expires_at, accepted_at
- match (OneToOne to ConnectFiveMatch, nullable)
- created_date, modified_date

ConnectFiveMatch:
- challenge (OneToOne)
- player_a, player_b (FK users.User)
- status, winner (nullable)
- active_player, turn_number, turn_started_at
- clock_a_remaining_ms, clock_b_remaining_ms
- prize_pool_total, max_spend_amount
- board_state (JSONField, 14x14 ints)
- finished_at, finish_reason

ConnectFiveMatchPlayer:
- match, user
- spent_total
- inventory_h2, inventory_v2, inventory_cross4, inventory_bomb
- last_action_at

ConnectFiveMatchEvent (audit log):
- match, actor (nullable for system)
- event_type (move, purchase, timeout, settlement)
- payload (JSON: coordinates, board delta, inventory delta)
- idempotency_key, wallet_ledger_refs
- created_date

ConnectFiveEscrow + LedgerEntry:
- match, currency (TNB)
- player_a_contrib, player_b_contrib, total
- status (locked, settled)
- LedgerEntry: wallet, amount, direction, action, idempotency_key

Board representation choice:
- JSONField storing a 14x14 list of small ints (0 empty, 1/2 players).
- Rationale: small size, easy validation, readable, no heavy DB constraints.
- Optional: store board_hash for integrity and faster change detection.

## 8. Frontend integration notes

### 8.1 Updates (polling vs realtime)
Preferred: websocket updates for match and challenge changes, with HTTP polling as fallback.
- Add consumer similar to wallets/exchange for:
  - `update.connect_five_match`
  - `create.connect_five_event`
  - `update.connect_five_challenge`
- Frontend should open match socket only when viewing a match.

### 8.2 Redux store shape (high level)
- `connectFive.challenges.byId`, `connectFive.matches.byId`
- `connectFive.matchEvents.byMatchId`
- `connectFive.activeMatchId`
- `connectFive.inventories.byMatchId.byUserId`
- `connectFive.clocks.byMatchId` (active_player, remaining_ms, turn_started_at)
- `connectFive.purchaseLimits.byMatchId` (max_spend, spent_total, remaining)

### 8.3 UI requirements
- Toolbar shows SINGLE (unlimited) plus H2, V2, CROSS4, BOMB with counters.
- Disable or grey out Specials with zero inventory.
- Purchase modal displays prices, remaining spend, prize pool.
- Clock display uses server time offset and turn_started_at to show live countdown.

## 9. Operational considerations
- Challenge expiry and match timeout sweeps must be reliable (Celery beat).
- Use `select_for_update` to avoid race conditions between sweeper and player actions.
- Log every state change in MatchEvent; include wallet ledger refs for disputes.
- Provide admin scripts or management commands for manual settlement or refunds.
- Alerts: log timeouts, unexpected state transitions, and escrow mismatches.
