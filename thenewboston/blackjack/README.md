# Blackjack

Blackjack version 1 is a server-authoritative, single-player game against the casino dealer. It shares the casino treasury, wallet transfers, commitments, receipts and reconciliation. Its migration enables the game with a 2 TNB minimum; it does not create or transfer funds.

## Rules

- Six decks, freshly shuffled for each hand.
- The dealer checks for a natural blackjack after dealing and stands on all 17s, including soft 17.
- A natural blackjack pays 3:2 profit. Other wins pay 1:1, ties return the stake, and losses return zero. Two naturals tie. A three-or-more-card 21 is an ordinary hand.
- Hit, Stand, or Double Down. Double is available only on the first decision, charges one additional original stake and draws exactly one card. A hit reaching 21 automatically begins the dealer's turn.
- No splitting, insurance or surrender.
- Initial wagers must be even whole TNB so every 3:2 payout is an exact integer. Return depends on player decisions; the catalog does not claim a fixed house edge or RTP.
- Hands automatically stand 15 minutes after acceptance. The deadline does not reset after a hit. A late client action also triggers this settlement if the worker has not run yet.

## API and recovery

Use the casino commitment and bet endpoints with `game: "blackjack"`, `rules_version: 1`, and no selection. A natural may settle immediately. Otherwise the receipt has `status: "open"` and a public `result` containing the player's cards and total, the dealer's up-card and visible total, a `null` hole card, `revision`, `available_actions`, and `expires_at`. The server seed, hole card, action transcript, and shuffle remain private until settlement.

`GET /api/casino/bets/active` returns the authenticated user's open casino receipt, or JSON `null`. The existing history and request-ID recovery endpoints also return the latest safe receipt. A replay of the original wager cannot charge again, even after game closure or settlement.

`POST /api/casino/bets/{request_id}/actions` accepts:

```json
{"action_id": "a fresh UUID", "action": "hit", "expected_revision": 0}
```

The other actions are `stand` and `double`. Reuse the exact payload when recovering a lost response. An accepted action ID returns the latest hand receipt without repeating the action; reuse with different details conflicts. A stale revision also conflicts. All endpoints are authenticated and ownership-scoped. A timed-out hand returns its automatic stand result without applying or charging the late requested action.

Settled results reveal both hands and totals, the recorded string `actions` array, `outcome`, `revision`, `multiplier` and `doubled`. Outcomes are `blackjack`, `win`, `loss` or `push`. `multiplier` describes total payout divided by the original wager: a blackjack is 2.5, a regular win is 2, a doubled win is 4, a regular push is 1, and a doubled push is 2. The receipt's `total_stake` includes a doubled stake and `profit` is payout minus total stake.

## Published shuffle and replay

Use the casino's `hmac-sha256-v1` generator with game `blackjack` and rules version 1. Card strings concatenate rank and suit, for example `AS`, `10H` or `QC`.

1. Construct six copies of a deck. For each copy, iterate suits `C, D, H, S`; within each suit iterate ranks `A, 2, 3, 4, 5, 6, 7, 8, 9, 10, J, Q, K`.
2. Fisher–Yates shuffle from index 311 down to 1. Draw `j = below(i + 1)` and swap indices `i` and `j`. The HMAC counter continues across all rejection-sampling calls.
3. Consume from the front. Player receives indices 0 and 2; dealer receives 1 and 3. Subsequent draws start at index 4.
4. Resolve initial naturals before actions. Replay each recorded action in order. A bust settles immediately without drawing dealer cards. After stand, double, or a hit reaching 21, the dealer draws until its total is at least 17. Aces count as 11 until that would bust, then as 1.
5. Timeout appends `stand`; the receipt marks `settlement_reason: "timeout"`. The seed proves card/result reproducibility, not who chose the recorded actions.

Reference vector: server seed `00` repeated 32 times, commitment ID `00000000-0000-0000-0000-000000000001`, client seed `vector-1`, actions `["double"]` gives player `6D, 2S, JS` (18), dealer `3H, 8H, 4S, 2C` (17), and multiplier 4. Engine tests share independent vectors with the browser verifier.

## Financial and worker behavior

Acceptance reserves the original stake plus twice that stake in house exposure. This precommitted exposure covers every permitted future action, including doubling after all free treasury funds have been withdrawn. A double increases treasury balance and reservation by exactly its additional stake; it never increases house exposure. Action identities and extra-stake ledger keys are unique. Payout settlement releases the entire reservation and records one payout ledger event, including zero payouts.

Placement, actions, and timeouts lock the singleton casino fund first, then the bet, then the wallet. Actions replay the committed shuffle and transcript and compare the full persisted result and stake/exposure before changing money. Corrupt state is never rerolled or silently refunded: the reservation stays protected and worker failures are logged. Safe-integer wallet limits are checked before deriving an action outcome; an externally filled wallet can temporarily prevent settlement until space is restored, with all reservations retained.

The `tasks.expire_blackjack_hands` Celery task runs every minute and processes up to 100 overdue hands. Repeated tasks and racing client actions settle once under database locks. Casino closure prevents new wagers but does not block completion of accepted hands. Existing instant-game recovery deliberately skips Blackjack. `verify_casino` verifies all installed rules and reconciles the shared ledger and open reservations.
