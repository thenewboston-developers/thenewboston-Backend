# Let It Ride

Let It Ride version 1 is five-card poker against a paytable, played alone against the casino. It shares the casino treasury, wallet transfers, commitments, receipts and reconciliation. Its migration enables the game with a 3 TNB minimum; it does not create or transfer funds, and the app has no tables of its own.

## Rules

- One 52-card deck, dealt fresh for every hand.
- The wager is three equal bets, so `amount` (their total) must be a multiple of 3.
- The player sees three cards and decides the first bet, sees the first community card and decides the second bet, then the second community card is turned. The third bet always plays.
- `ride` leaves a bet on the table and `pull` takes it back. A pulled bet is returned in the payout when the hand settles, moments later; nothing moves between the deal and the payout.
- Each bet still riding at the end is paid on the five-card hand, to one, and is returned as well. Any other hand loses the riding bets. An ace plays high or low in a straight (`A-2-3-4-5` and `10-J-Q-K-A`).

| Hand | Pays |
| --- | --- |
| Royal flush | 100 to 1 |
| Straight flush | 50 to 1 |
| Four of a kind | 25 to 1 |
| Full house | 15 to 1 |
| Flush | 10 to 1 |
| Straight | 6 to 1 |
| Three of a kind | 3 to 1 |
| Two pair | 2 to 1 |
| Pair of tens or better | 1 to 1 |

With bet `b = amount / 3`, `r` bets riding and odds `o`, the payout is `b * (3 - r)`, plus `b * r * (o + 1)` when the hand pays.

The top prize is 100 to 1 rather than the 1,000 to 1 of a casino floor, so that the fund can cover three riding bets at a useful stake; the middle of the table (full house, flush, straight) pays more than usual in return. A later rules version can raise the top prizes when the fund is larger.

## Return and strategy

With the best decision on every hand the expected loss is exactly `7979 / 249900` (3.19%) of one bet, which is 1.06% of the three bets staked. The classic 1,000/200/50/11/8/5/3/2/1 table loses 3.51% of one bet under the same calculation. The catalog reports both figures (`house_edge` per amount staked and `house_edge_per_bet`).

The best play is short enough to print, and the rules page does:

- First bet (three cards): let it ride with a pair of tens or better or three of a kind; with three suited cards in a row or with one gap, when at least one is a ten or higher; with three suited cards with two gaps, when at least two are tens or higher; and with ten, jack, queen in any suits. Aces count high here.
- Second bet (four cards): let it ride with any hand that already pays; with four cards of one suit; with four cards in a row from `2-3-4-5` to `10-J-Q-K`; and with four different cards that are all tens or higher.

`tests/test_engine.py` proves the hand frequencies, the house edge and that this strategy is the best decision for every possible deal, in under a second.

## API and recovery

Use the casino commitment and bet endpoints with `game: "let_it_ride"`, `rules_version: 1` and no selection. The receipt comes back with `status: "open"` and a public `result`:

```json
{
  "cards": ["QS", "3H", "7S"],
  "community": [null, null],
  "decisions": [],
  "revision": 0,
  "phase": "first",
  "riding": 3,
  "hand": null,
  "odds": null,
  "available_actions": ["ride", "pull"],
  "expires_at": "2026-11-25T22:10:00+00:00"
}
```

`phase` is `first`, `second` or `settled`. A community card is `null` until the decision before it has been made, and the server seed stays hidden until the hand settles. `GET /api/casino/bets/active` returns the open hand on any device, and the history and request-ID endpoints return the same safe receipt.

`POST /api/casino/bets/{request_id}/actions` accepts:

```json
{"action_id": "a fresh UUID", "action": "ride", "expected_revision": 0}
```

`expected_revision` is the number of decisions already made (0, then 1). Reuse the exact payload to recover a lost response: an accepted action ID returns the latest receipt without repeating the action. The same ID with a different action or revision is a 409 `request_conflict`, a stale revision is a 409 `revision_conflict`, and acting on a finished hand is a 409 `hand_settled`.

A settled result adds both community cards, `hand` (a paytable key or `no_win`) and `odds` (0 when the hand does not pay). The catalog entry includes `bets: 3`, `bet_increment: 3`, a `paytable` of `{hand, odds}`, `house_edge_per_bet` and `timeout_seconds`.

## Timeout

A hand left unfinished 10 minutes after the deal is settled by the `tasks.expire_let_it_ride_hands` Celery task, which runs every 30 seconds and processes up to 100 overdue hands. A late action settles the hand the same way instead of being applied. The receipt's `settlement_reason` is then `timeout`.

Each undecided bet rides only if the cards already shown hold a paying hand, which no later card can take away; otherwise it is pulled back. A timeout therefore never loses a bet the player did not choose to risk, and never gives up a win that was already certain.

## Published deal and replay

Use the casino's `hmac-sha256-v1` generator with game `let_it_ride` and rules version 1. Card strings concatenate rank and suit, for example `AS`, `TH` or `2C`.

1. Start from the deck in order `2C, 2D, 2H, 2S, 3C ... AS`: ranks `23456789TJQKA`, and within each rank suits `C, D, H, S`.
2. Five times: draw `d = below(cards left)` and remove the card at index `d`. The bounds are 52, 51, 50, 49 and 48, and the HMAC counter continues across rejection-sampling calls.
3. The first three cards are the player's; the last two are the community cards in the order they are turned.
4. Replay the recorded `decisions` to count the riding bets, rank all five cards, and apply the paytable. Decisions never change which cards are dealt.

Reference vectors with server seed `00` repeated 32 times and commitment ID `00000000-0000-0000-0000-000000000001`: client seed `test-client` deals `QS 3H 7S` then `TH JH` (no paying hand); `vector-0` deals `KH JS TD` then `QD 9C` (a straight); `vector-44` deals `4D 4H 4C` then `TH 4S` (four of a kind). The browser verifier asserts the same vectors.

## Financial and worker behavior

Acceptance takes all three bets and reserves them together with the largest possible win: `101 * amount` in total, enough for three riding bets on a royal flush. No action adds a stake or changes the reservation. Settlement goes through the casino's shared `pay_out`, which releases the whole reservation and records one payout ledger event, including a zero payout.

Placement, actions and timeouts lock the singleton casino fund first, then the bet, then the wallet. Before any decision or payout the server re-deals the hand from its committed seed, replays the recorded decisions and compares the whole stored state, the stake and the exposure; a hand that does not match is never rerolled or refunded, keeps its reservation and raises an error. The safe-integer wallet limit is checked before the next card is used. Casino or game closure blocks new deals but never a hand already in play. Instant-game recovery skips Let It Ride, and `verify_casino` verifies its paytable and hand ranking and reconciles the open reservations.
