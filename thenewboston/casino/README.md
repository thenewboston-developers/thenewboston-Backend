# Casino

The casino is independent of `game_rewards.GameFund`. Migrations create an **empty** fund and enable Slots, Roulette, Plinko, and Blackjack; they never mint or transfer coins. A staff user deposits existing TNB through the casino UI/API. With 100,000 TNB available and the default 1% exposure limit, maximum wagers are 10 TNB on 100x Slots, 1,000 TNB on even-money Roulette, 28 TNB on a single number, 20 TNB on 50x Plinko, and 500 TNB on Blackjack (covering double down).

`casino` owns the shared fund, ledger, commitments, bets, API, settlement, and reconciliation. `slots`, `roulette`, `plinko`, and `blackjack` are separate Django apps that own their game rules, catalog metadata, and gameplay tests. Each app registers an immutable `GameDefinition` from `AppConfig.ready()`; shared services consume `GameRules` through the generic registry. [Blackjack](../blackjack/README.md) adds interactive hands, safe action retries, double-down stakes and timeout settlement without changing historical Slots, Roulette or Plinko behavior.

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

Instant games settle in the same transaction as acceptance. Animations are presentation only. A lost response is recovered by request ID or by replaying the exact request, including its seed and selection. A new ID means a new wager. Interactive games retain their reservation across actions and redact their public result until settlement; each installed interactive ruleset owns its lifecycle hooks.

`verify_casino` performs read-only ledger/reservation reconciliation and invokes every installed ruleset's own mathematical checks. A Celery task repeats reconciliation every minute and recovers unexpectedly open **instant** games from their persisted, verified outcome. A corrupt outcome retains its reservation and emits an error; it is never rerolled or silently refunded. Game closure only blocks new bets.

## API

Routes have no trailing slash and use the existing API authentication:

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/api/casino` | Public fund, rules, dynamic limits; authenticated staff receive `can_manage: true`. |
| POST | `/api/casino/commitments` | Authenticated, single-use pre-bet seed commitment, valid for 10 minutes. |
| POST | `/api/casino/bets` | Submit `request_id`, `commitment_id`, `client_seed`, `game`, `rules_version`, integer `amount`, and optional `selection`. |
| GET | `/api/casino/bets` | Own last 20 receipts. |
| GET | `/api/casino/bets/active` | Own open receipt, or JSON `null`. |
| GET | `/api/casino/bets/{request_id}` | Own request recovery; 404 means no committed bet with this ID. |
| POST | `/api/casino/bets/{request_id}/actions` | Interactive action with UUID `action_id`, `action` and integer `expected_revision`. |
| POST | `/api/casino/fund/deposits` | Staff-only transfer from own TNB wallet; integer `amount` and UUID `request_id`. |
| POST | `/api/casino/fund/withdrawals` | Staff-only transfer of free funds to own TNB wallet; same input. |

Roulette selection is `{type}` for red/black/odd/even/low/high, `{type: "dozen"|"column", value: 1..3}`, or `{type: "number", value: 0..36}`. Slots, Plinko and Blackjack accept no selection (omit it, send `null`, or send `{}`). Plinko version 1 has a fixed twelve-row board and payout table; clients cannot choose a path, pocket, or risk profile. Amounts must be JSON integers, not floats, booleans, or strings. Blackjack additionally requires even wagers for exact 3:2 payouts. A closed or underfunded game rejects before charging. Casino service errors preserve `{code, detail, max_bet?, min_bet?, fund?}`; request identity conflicts return 409.

Financial rows are read-only in Django admin. Fund enabled/risk settings and game enabled/minimum/rules version are editable under locks, and stale admin forms cannot overwrite money. Only installed rules versions may be selected. Admin funding is not a community donation or an investment scheme; no automatic transfer to GameFund exists.

## Published fairness algorithm: hmac-sha256-v1

1. Before wagering, receive the server commitment hash and UUID. The secret is 32 random bytes encoded as 64 lowercase hexadecimal characters. The commitment hash is SHA-256 of those **64 ASCII characters**.
2. Generate a fresh browser client seed after receiving the commitment. It must be 1–128 printable ASCII characters. Submit it with the wager and rules version.
3. HMAC-SHA256 key: decode the server seed hex into 32 bytes. Message: compact JSON encoding of `["casino-v1", game, rules_version, commitment_id, client_seed, counter]`, with no spaces. Counter begins at zero; UUID is its lowercase hyphenated string.
4. Interpret the first eight digest bytes as an unsigned, big-endian 64-bit integer `n`. For bound `b`, reject `n >= 2^64 - (2^64 % b)` and increment the counter. Otherwise use `n % b`. The bounds are 10,000 for Slots, 37 for Roulette, and 4,096 for Plinko.
5. The server reveals the seed on the settled receipt. Recompute its hash and outcome. Every commitment is usable for at most one accepted bet and is never reused after reveal.

Slots outcome intervals, in order, have `(multiplier, weight)` values `(0, 5885), (1, 1600), (2, 2000), (5, 400), (10, 100), (50, 10), (100, 5)`. Multipliers are total return including stake. Weights sum to 10,000 and weighted payouts to 9,600: 96% RTP. The matching reel symbols visualize this weighted outcome; reels are not independently sampled.

Slots rules version 2 is current; version 1 stays installed so its receipts still settle and verify. Both use the same intervals and payouts, and a winning draw shows its three matching symbols (`cherry` 1x, `lemon` 2x, `bell` 5x, `bar` 10x, `diamond` 50x, `seven` 100x). They differ only in the symbols of a losing draw `d`:

- Version 1 always shows `cherry, lemon, bar`.
- Version 2 shows line `d % 120` of the 120 ordered lines of three different symbols, in `itertools.permutations(('cherry', 'lemon', 'bell', 'bar', 'diamond', 'seven'), 3)` order: line 0 is `cherry, lemon, bell` and line 119 is `seven, diamond, bar`. A losing spin therefore never shows a matching pair, and its symbols never affect a payout.

Roulette is single-zero, uniform 0–36, with 2x outside bets, 3x dozens/columns and 36x single-number total returns. Zero loses all outside bets. Every offered selection has RTP 36/37. All current payouts are exact whole TNB.

Plinko version 1 makes one uniform draw `d` from 0–4095. Read its twelve binary digits from most significant to least significant, retaining leading zeroes: 0 means bounce left and 1 means bounce right. The zero-indexed landing pocket is the sum of those digits. Its thirteen total-return multipliers from left to right are `[50, 18, 8, 3, 1, 0, 0, 0, 1, 3, 8, 18, 50]`; every payout is an exact whole TNB including any returned stake. Pocket `k` has probability `C(12, k) / 4096`, giving RTP `3898 / 4096 = 95.166015625%` and house edge `4.833984375%`. The center three pockets pay zero. The animation replays the accepted result and cannot affect settlement.

The Plinko catalog includes `rows: 12` and a `payout_table` of `{slot, multiplier, probability}` entries. Its receipt result is `{draw, path, slot, multiplier}`. A public verification vector with server seed 64 zeroes, client seed `test-client`, commitment UUID `00000000-0000-0000-0000-000000000001`, game `plinko`, and version 1 produces draw 366, path `[0, 0, 0, 1, 0, 1, 1, 0, 1, 1, 1, 0]`, pocket 6, and multiplier 0.

Migration `0004_plinko` enables a previously unconfigured game without transferring funds or changing existing configuration. Its reverse disables Plinko and retains financial history and configuration; after reversing and reapplying, an administrator must explicitly re-enable that retained configuration.

Unrevealed seeds are encrypted using a domain-separated key derived from Django `SECRET_KEY`, and excluded from API/admin output. Keep that key stable until outstanding commitments expire and all open bets settle. Settled receipts retain revealed seeds so verification survives later rotation. Verification demonstrates result reproducibility; it does not replace the ledger or funding constraints.

## Adding games

Create a Django game app that implements `casino.contracts.GameRules`, provides a `GameDefinition` catalog descriptor, and registers it in `AppConfig.ready()`. Install the app and explicitly configure its shared `CasinoGameConfig` row. The registry exposes installed game IDs to serializers and supplies rules to the catalog, admin validation, settlement, recovery, and deployment verification; shared casino code needs no branches for a new game name. Treasury limit arithmetic stays shared, while game-specific catalog data receives a callback for displaying those limits.

Register all historical immutable `(game, version)` rules, even after selecting a newer version in configuration. Never change a historical game's identity, selection normalization, outcome mapping, or fairness draw sequence. The current rules registry records settlement mode, and instant recovery deliberately excludes future interactive games. An interactive game must implement its own action IDs, revision checks, timeout behavior and settlement handler; it must protect permitted future actions at acceptance and preserve the lock order and ledger invariants. Future additional stakes use unique per-action ledger event keys and increase both fund balance and reservation without increasing precommitted house exposure.
