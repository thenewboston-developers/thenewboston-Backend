# Video Poker

Video Poker version 1 is server-authoritative, single-player Jacks or Better. It shares the casino treasury, wallet transfers, commitments, receipts and reconciliation. Its migration enables the game with a 1 TNB minimum; it does not create or transfer funds.

## Rules

- One 52-card deck, freshly shuffled for each hand.
- Five cards are dealt face up. The player holds any of them (none, some or all) and draws once; every card that is not held is replaced from the same deck. The hand after the draw is final.
- Aces play high or low in a straight: `A-2-3-4-5` and `10-J-Q-K-A` both count, `Q-K-A-2-3` does not.
- A pair pays only when it is jacks, queens, kings or aces.
- No wild cards, no doubling, no second draw.
- A hand left open is drawn with all five cards held 15 minutes after the deal, so it is paid as dealt. A late client action also triggers this settlement if the worker has not run yet.

Payouts are total returns including the wager, the classic "9/6" table with a flat royal flush:

| Hand | Total return |
| --- | --- |
| Royal flush | 250x |
| Straight flush | 50x |
| Four of a kind | 25x |
| Full house | 9x |
| Flush | 6x |
| Straight | 4x |
| Three of a kind | 3x |
| Two pair | 2x |
| Jacks or better | 1x |

Every payout is a whole number of TNB for every whole wager.

## Return

Return depends on the cards the player holds. The strategy that maximizes the expected payout of every dealt hand returns `35,523,565,111 / 36,110,924,850 = 98.3734569%` of wagers, a house edge of `1.6265431%`. This figure comes from enumerating all 2,598,960 deals, all 32 ways to hold each one and every possible draw. The catalog publishes it as `optimal_return`, with `house_edge` as its complement and a note that it assumes perfect play; any other strategy returns less. Holding every dealt card, which is what a timeout does, returns `873,304 / 2,598,960 = 33.6%`.

The 2,598,960 five-card hands fall into the categories as 4 royal flushes, 36 straight flushes, 624 four of a kinds, 3,744 full houses, 5,108 flushes, 10,200 straights, 54,912 three of a kinds, 123,552 two pairs, 337,920 pairs of jacks or better and 2,062,860 losing hands. `verify_casino` recounts them on every deployment.

## API and recovery

Use the casino commitment and bet endpoints with `game: "video_poker"`, `rules_version: 1`, and no selection. The receipt has `status: "open"` and a public `result` containing `dealt` and `hand` (the same five cards before the draw), `held: null`, `category` (what the hand makes as it stands), `phase: "draw"`, `revision: 0`, `available_actions: ["draw"]`, and `expires_at`. The server seed and the rest of the shuffle remain private until settlement; the stored hand never contains an undealt card.

`GET /api/casino/bets/active` returns the authenticated user's open casino receipt, or JSON `null`. The existing history and request-ID recovery endpoints also return the latest safe receipt. A replay of the original wager cannot charge again, even after game closure or settlement.

`POST /api/casino/bets/{request_id}/actions` accepts:

```json
{"action_id": "a fresh UUID", "action": "draw:10110", "expected_revision": 0}
```

The five digits after `draw:` follow the dealt cards from left to right: `1` holds a card and `0` replaces it. `draw:11111` keeps the dealt hand and `draw:00000` replaces all of it. Reuse the exact payload when recovering a lost response. An accepted action ID returns the settled receipt without drawing again; reuse with different details conflicts, and so does any new action on a settled hand. All endpoints are authenticated and ownership-scoped. A timed-out hand returns its automatic result without applying the late requested holds.

Settled results reveal `dealt`, `held` (five booleans), the final `hand`, `category`, `multiplier`, the recorded `actions` array and `revision: 1`. Categories are `royal_flush`, `straight_flush`, `four_of_a_kind`, `full_house`, `flush`, `straight`, `three_of_a_kind`, `two_pair`, `jacks_or_better` and `nothing`. The receipt's `payout` is the wager times `multiplier` and `profit` is payout minus the wager.

## Published shuffle and replay

Use the casino's `hmac-sha256-v1` generator with game `video_poker` and rules version 1. Card strings concatenate rank and suit, for example `AS`, `10H` or `QC`.

1. Construct one deck: iterate suits `C, D, H, S`; within each suit iterate ranks `A, 2, 3, 4, 5, 6, 7, 8, 9, 10, J, Q, K`.
2. Fisher–Yates shuffle from index 51 down to 1. Draw `j = below(i + 1)` and swap indices `i` and `j`. The HMAC counter continues across all rejection-sampling calls.
3. The dealt hand is indices 0 to 4, in order.
4. Replay the recorded action. Walk the dealt hand from left to right; each card that is not held is replaced by the next unused card starting at index 5. Held cards keep their positions.
5. Evaluate the final five cards and pay the table above. A timeout records `draw:11111`; the receipt marks `settlement_reason: "timeout"`. The seed proves card and result reproducibility, not who chose the recorded holds.

Reference vectors use server seed `00` repeated 32 times and commitment ID `00000000-0000-0000-0000-000000000001`:

- Client seed `vector-1` deals `3D, 2S, 9D, 3S, QC` with `9S, QD, 10S, KH, 2H` next in the deck. `draw:10110` gives `3D, 9S, 9D, 3S, QD`: two pair, multiplier 2.
- Client seed `test-client` deals `8D, 9H, 6H, AD, 10S` with `3D, JD, QD, 8S, 4D` next. `draw:10010` gives `8D, 3D, JD, AD, QD`: a flush, multiplier 6.

Engine tests share these vectors with the browser verifier.

## Financial and worker behavior

Acceptance reserves the wager plus 249 times the wager in house exposure, so a royal flush is covered from the moment of the deal, including after all free treasury funds have been withdrawn. The draw adds no stake. Settlement releases the entire reservation and records one payout ledger event, including zero payouts.

Placement, the draw, and timeouts lock the singleton casino fund first, then the bet, then the wallet. The draw replays the committed shuffle and compares the full persisted hand and stake/exposure before changing money. Corrupt state is never rerolled or silently refunded: the reservation stays protected and worker failures are logged. Safe-integer wallet limits are checked before any replacement card is derived; an externally filled wallet can temporarily prevent settlement until space is restored, with all reservations retained.

The `tasks.expire_video_poker_hands` Celery task runs every minute and processes up to 100 overdue hands. Repeated tasks and racing client actions settle once under database locks. Casino closure prevents new wagers but does not block completion of accepted hands. Existing instant-game recovery deliberately skips Video Poker. `verify_casino` verifies all installed rules and reconciles the shared ledger and open reservations.
