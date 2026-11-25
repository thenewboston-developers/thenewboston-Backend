# Casino

The casino is independent of `game_rewards.GameFund`. Migrations create an **empty** fund and enable Slots and Roulette; they never mint or transfer coins. A staff user deposits existing TNB through the casino UI/API. With 100,000 TNB available and the default 1% exposure limit, maximum wagers are 10 TNB on 100x Slots, 1,000 TNB on even-money Roulette, and 28 TNB on a single number.

`casino` owns the shared fund, ledger, commitments, bets, API, settlement, and reconciliation. `slots` and `roulette` are separate Django apps that own their game rules, catalog metadata, and gameplay tests. Each app registers an immutable `GameDefinition` from `AppConfig.ready()`; shared services consume `GameRules` through the generic registry. The extraction does not move database tables or change stored game IDs, rules versions, fairness receipts, or `/api/casino` endpoints.

## Money and locking

All financial operations run in `transaction.atomic()` and acquire the singleton casino fund first, then an existing bet/config/commitment as needed, then the wallet. Wallet mutations use the existing wallet service and publish only after commit. Never acquire the casino fund after locking a wallet.

- `balance = deposits + stakes - payouts - withdrawals` (payouts include returned stakes).
- `reserved = sum(total_stake + house_exposure)` across open bets.
- `available = balance - reserved`; this value is never stored.
- `0 <= reserved <= balance` is a database constraint.
- A bet's net house exposure is at most `available * risk_limit_bps // 10000`, evaluated before its stake enters the fund.
- Initial and subsequent stakes must remain protected alongside fixed house exposure. Otherwise stakes would appear withdrawable.
- Every accepted bet has one `(user, request_id)` identity and one payout ledger event. Ledger `event_key` supports distinct additional-stake actions for future games.
- Admin deposit/withdrawal IDs share a unique `(user, request_id)` namespace; changing amount or operation on a retry conflicts.

Version 1 games settle in the same transaction as acceptance. Animations are presentation only. A lost response is recovered by request ID or by replaying the exact request, including its seed and selection. A new ID means a new wager.

`verify_casino` performs read-only ledger/reservation reconciliation and invokes every installed ruleset's own mathematical checks. A Celery task repeats reconciliation every minute and recovers unexpectedly open **instant** games from their persisted, verified outcome. A corrupt outcome retains its reservation and emits an error; it is never rerolled or silently refunded. Game closure only blocks new bets.

## API

Routes have no trailing slash and use the existing API authentication:

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/api/casino` | Public fund, rules, dynamic limits; authenticated staff receive `can_manage: true`. |
| POST | `/api/casino/commitments` | Authenticated, single-use pre-bet seed commitment, valid for 10 minutes. |
| POST | `/api/casino/bets` | Submit `request_id`, `commitment_id`, `client_seed`, `game`, `rules_version`, integer `amount`, and optional `selection`. |
| GET | `/api/casino/bets` | Own last 20 receipts. |
| GET | `/api/casino/bets/{request_id}` | Own request recovery; 404 means no committed bet with this ID. |
| POST | `/api/casino/fund/deposits` | Staff-only transfer from own TNB wallet; integer `amount` and UUID `request_id`. |
| POST | `/api/casino/fund/withdrawals` | Staff-only transfer of free funds to own TNB wallet; same input. |

Roulette selection is `{type}` for red/black/odd/even/low/high, `{type: "dozen"|"column", value: 1..3}`, or `{type: "number", value: 0..36}`. Slots accepts no selection. Amounts must be JSON integers, not floats, booleans, or strings. A closed or underfunded game rejects before charging. Casino service errors preserve `{code, detail, max_bet?, min_bet?, fund?}`; request identity conflicts return 409.

Financial rows are read-only in Django admin. Fund enabled/risk settings and game enabled/minimum/rules version are editable under locks, and stale admin forms cannot overwrite money. Only installed rules versions may be selected. Admin funding is not a community donation or an investment scheme; no automatic transfer to GameFund exists.

## Published fairness algorithm: hmac-sha256-v1

1. Before wagering, receive the server commitment hash and UUID. The secret is 32 random bytes encoded as 64 lowercase hexadecimal characters. The commitment hash is SHA-256 of those **64 ASCII characters**.
2. Generate a fresh browser client seed after receiving the commitment. It must be 1–128 printable ASCII characters. Submit it with the wager and rules version.
3. HMAC-SHA256 key: decode the server seed hex into 32 bytes. Message: compact JSON encoding of `["casino-v1", game, rules_version, commitment_id, client_seed, counter]`, with no spaces. Counter begins at zero; UUID is its lowercase hyphenated string.
4. Interpret the first eight digest bytes as an unsigned, big-endian 64-bit integer `n`. For bound `b`, reject `n >= 2^64 - (2^64 % b)` and increment the counter. Otherwise use `n % b`. The bounds are 10,000 for Slots and 37 for Roulette.
5. The server reveals the seed on the settled receipt. Recompute its hash and outcome. Every commitment is usable for at most one accepted bet and is never reused after reveal.

Slots outcome intervals, in order, have `(multiplier, weight)` values `(0, 5885), (1, 1600), (2, 2000), (5, 400), (10, 100), (50, 10), (100, 5)`. Multipliers are total return including stake. Weights sum to 10,000 and weighted payouts to 9,600: 96% RTP. The matching reel symbols visualize this weighted outcome; reels are not independently sampled.

Roulette is single-zero, uniform 0–36, with 2x outside bets, 3x dozens/columns and 36x single-number total returns. Zero loses all outside bets. Every offered selection has RTP 36/37. All current payouts are exact whole TNB.

Unrevealed seeds are encrypted using a domain-separated key derived from Django `SECRET_KEY`, and excluded from API/admin output. Keep that key stable until outstanding commitments expire and all open bets settle. Settled receipts retain revealed seeds so verification survives later rotation. Verification demonstrates result reproducibility; it does not replace the ledger or funding constraints.

## Adding games

Create a Django game app that implements `casino.contracts.GameRules`, provides a `GameDefinition` catalog descriptor, and registers it in `AppConfig.ready()`. Install the app and explicitly configure its shared `CasinoGameConfig` row. The registry exposes installed game IDs to serializers and supplies rules to the catalog, admin validation, settlement, recovery, and deployment verification; shared casino code needs no branches for a new game name. Treasury limit arithmetic stays shared, while game-specific catalog data receives a callback for displaying those limits.

Register all historical immutable `(game, version)` rules, even after selecting a newer version in configuration. Never change a historical game's identity, selection normalization, outcome mapping, or fairness draw sequence. The current rules registry records settlement mode, and instant recovery deliberately excludes future interactive games. An interactive game must implement its own action IDs, revision checks, timeout behavior and settlement handler; it must protect permitted future actions at acceptance and preserve the lock order and ledger invariants. Future additional stakes use unique per-action ledger event keys and increase both fund balance and reservation without increasing precommitted house exposure.
