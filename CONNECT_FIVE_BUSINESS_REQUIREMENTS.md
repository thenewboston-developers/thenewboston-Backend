# Business Requirements: Connect-5 + Specials + Mandatory Stake (TNB)

## 1. Overview

Build a 2-player, turn-based strategy game played on a 14x14 grid. Players place pieces on any empty cell (no gravity). The first player to create 5 connected pieces in a row (horizontal, vertical, or diagonal) wins immediately. The game includes purchasable “Specials” that modify what a player can do on their turn. All wagering, purchases, and prize pools use TNB only.

---

## 2. Core Game Rules

### 2.1 Players

* Exactly two players per match: Player A and Player B.

### 2.2 Board

* The board is a 14x14 grid.
* A cell can be either empty or occupied by Player A’s piece or Player B’s piece.
* Pieces can be placed on any empty cell.

### 2.3 Winning

* A player wins immediately when their action results in 5 of their pieces connected in a straight line (horizontal, vertical, or diagonal).
* The match ends as soon as a win condition is created.

### 2.4 Draws

* Draws are possible.
* If the match ends in a draw, all locked funds are refunded to both players (see Payouts).

---

## 3. Mandatory Stake, Prize Pool, and Spending

### 3.1 Currency

* The only supported currency is TNB.

### 3.2 Challenge creation requirements

When Player A creates a challenge, they must choose:

* The required stake amount each player must put up to play (the “ante”).
* A maximum additional amount each player is allowed to spend on Specials during the match (the “max spend”).
* The total time each player has to make moves across the entire match (chess-style clock).

### 3.3 Accept window

* A challenge must be accepted within 5 minutes of being created.
* If not accepted within 5 minutes, the challenge is automatically canceled and the challenger’s locked stake is returned to their wallet.

### 3.4 Prize pool behavior

* When a challenge is accepted, both players’ stakes are locked into a single prize pool.
* Any spending on Specials increases the prize pool.
* Each player can spend up to the max spend amount on Specials during the match.

### 3.5 Betting is required

* Every match must be created with a stake and max spend and requires the opponent to accept those terms.

---

## 4. Time Controls (Chess-style)

### 4.1 Player clocks

* Each player begins the match with a fixed total amount of time.
* Only the active player’s clock counts down.
* When the turn changes, the active clock switches immediately: the previous player’s clock stops and the next player’s clock starts.

### 4.2 Timeout

* If a player runs out of total time, they lose the match immediately and the opponent wins.

---

## 5. Turn Structure and Actions

### 5.1 Turn-based play

* Only the active player may take a move action that changes the board.
* Players alternate turns until the match ends via win, timeout, or draw.

### 5.2 Purchases

* Players may purchase Specials at any time, including during the opponent’s turn.
* Purchasing does not consume a turn.
* Purchases are limited by the max spend amount chosen at challenge creation.
* Purchased Specials are added to that player’s inventory.

### 5.3 Move action

On a player’s turn, they may perform exactly one of the following:

* Place a normal single piece.
* Use exactly one Special from their inventory.

The player cannot do both in the same turn.

---

## 6. Specials

### 6.1 General rules

* Specials are purchased using TNB, limited by the max spend amount per player.
* Specials can be purchased at any time but can only be used on the player’s own turn.
* Specials do not have per-match caps beyond the player’s max spend and what they choose to purchase.
* Any piece placed by a Special becomes a normal piece after placement for all practical purposes.

### 6.2 Special types (v1)

#### 6.2.1 Normal single piece (not purchased)

* Places one piece on an empty cell.

#### 6.2.2 Two-piece horizontal

* Places two pieces in two empty adjacent cells side by side (horizontal).
* Valid only if both target cells are empty.

#### 6.2.3 Two-piece vertical

* Places two pieces in two empty adjacent cells stacked vertically.
* Valid only if both target cells are empty.

#### 6.2.4 Four-piece cross

* Places four pieces around a center point:

  * One above, one below, one left, and one right of a chosen center cell.
* The center cell is not filled by this Special.
* Valid only if all four placement cells are within the board and empty.

#### 6.2.5 Bomb

* Removes exactly one opponent piece from the board.
* Valid only when targeting a cell occupied by the opponent.
* Cannot target an empty cell.
* Cannot target your own piece.

### 6.3 Bomb interaction with multi-piece placements

* If a bomb destroys a piece that was originally placed as part of a two-piece or four-piece Special, it still destroys only that single piece.

### 6.4 Invalid actions

* A move is invalid if it violates placement rules (occupied cells, out-of-bounds placement, invalid bomb target, etc.).
* The UI must clearly show when a move is invalid before the player commits it.
* Invalid moves must not change the board state.

---

## 7. Match End and Payouts

### 7.1 Win payout

* When a player wins (connect-5 or opponent timeout), the winning player receives the entire prize pool.

### 7.2 Draw payout

* If the match ends in a draw, both players receive refunds of:

  * Their original stake, plus
  * Any additional amount they spent on Specials during the match

---

## 8. UI Requirements

### 8.1 Board screen

Must display:

* The 14x14 grid and all placed pieces.
* Whose turn it is.
* Each player’s remaining time.
* The total prize pool amount.
* Each player’s remaining spendable amount (how much they can still spend on Specials).
* Each player’s current inventory of Specials (type and quantity).

### 8.2 Specials toolbar (bottom)

* A bottom toolbar shows the player’s available move options.
* Selecting an option changes the cursor/tool mode for placement or targeting.
* If a player has multiple of a Special, show a numeric counter on the icon.
* The normal single piece does not require a counter (unlimited).

Toolbar options must include:

1. Normal single piece
2. Two-piece horizontal
3. Two-piece vertical
4. Four-piece cross
5. Bomb

### 8.3 Hover preview and validation feedback

* When a player selects a move option and hovers over the board, the UI shows a preview of the affected cells.
* The preview must visibly indicate validity:

  * Valid placements/targets show a normal preview.
  * Invalid placements/targets show a red overlay (or equivalent clear invalid indicator).
    Examples of invalid states:
* Placing on occupied cells.
* Any part of a multi-piece placement overlaps an occupied cell.
* Bomb targeting an empty cell or the player’s own piece.

### 8.4 Purchasing interface

* A player can open a purchasing interface at any time.
* It must display:

  * Available Specials and their costs
  * The player’s remaining spendable amount
  * The player’s current inventory counts
  * The current prize pool total
* Purchasing a Special updates inventory, spend remaining, and the prize pool.

### 8.5 No “opponent shopping” indicator

* The UI should not show whether the opponent is currently shopping.

---

## 9. Acceptance Criteria

A v1 release is complete when:

* A player can create a challenge by selecting stake, max spend, and total time per player.
* A challenge expires after 5 minutes if not accepted and returns the challenger’s locked stake.
* On acceptance, a match starts and the prize pool is locked.
* Players can place normal pieces and use purchased Specials according to the rules.
* Players can purchase Specials at any time, limited by max spend.
* Prize pool grows as Specials are purchased.
* Clocks behave like chess (only active player time decreases); timeout ends the match immediately.
* Connect-5 ends the match immediately when formed.
* Draws are supported and result in refunds to both players of stake plus their own Special spending.
* The UI shows board state, both players’ time remaining, both players’ Special inventories, both players’ remaining spend amounts, and the total prize pool.
* The UI supports tool selection, hover previews, and clear invalid-state feedback.
