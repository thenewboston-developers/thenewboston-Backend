# Connect Five: Business Requirements

## Current Functionality Review (Connect Five)
- Navigation currently includes a Lobby and a Leaderboard for Connect Five.
- Lobby (current homepage) supports direct player challenges:
  - Challenge creation includes opponent selection, stake amount (TNB), max spend (TNB), and total time per player.
  - Incoming and outgoing challenges are listed separately; challenges can be accepted, declined, or cancelled.
  - Challenges expire if not accepted within a short window.
- Matches:
  - Active games and game history are shown in separate lists; history is paginated.
  - Matches can end by Connect Five or timeout; if a game ends with no Connect Five, the player who moved first loses (no draws).
  - Rematches are supported after completed games.
- Gameplay rules and economy:
  - Standard Connect Five on a 15x15 board.
  - Players can purchase special move types using TNB during a match (horizontal two, vertical two, bomb).
  - Each match has a max spend limit per player and a total time per player.
  - Prize pools are funded by stakes and in-game purchases; the winner takes the pool.
- ELO and leaderboard:
  - Each user has an ELO rating and win/loss stats.
  - Leaderboard ranks players by ELO and shows record.
- Live updates:
  - Challenge and match updates are streamed to participants in real time.
  - Background jobs handle challenge expiration and match timeouts.

## New Requirements: Connect Five Tournaments

### Navigation
The Connect Five section will have three main pages in the top navigation:
- Dashboard
- Tournaments
- Leaderboard

### Dashboard
The dashboard (replacing the current homepage) must include:
- Incoming challenges
- Outgoing challenges
- Active games (including tournament games)
- Game history (paginated)
- Time until the user's next tournament game (shown only when the user is registered for an upcoming tournament)
- The user's current ELO

### Tournaments Page (List View)
At the top of the page:
- A large hero banner highlighting the next major upcoming tournament.
- The hero tournament is selected manually by the site admin (placeholder only; no automated selection logic yet).

Below the hero:
- Cards for each upcoming tournament.
- Each card includes:
  - A small banner image for the tournament.
  - Tournament name.
  - Quick details (example: "Starts Jan 25, 2025 - 2:00 PM EST - 12/16 Players").
  - A single call-to-action button that displays one of the following states:
    - "Register Now"
    - "Full"
    - "Registration opens in 14h 32m" (countdown until registration opens)
    - "Registered" (with a checkmark icon)

Clicking a card routes the user to the tournament details page.

### Registration Rules
- Registration opens 1 hour before the tournament start time (fixed for all tournaments).
- Registration closes at the start time.
- Users can register or remove their registration until the start time.
- If a user unregisters before the start time, their buy-in (if any) is refunded.
- If the tournament reaches maximum players before the start time, registration closes and the CTA shows "Full".
- At the start time, if the minimum player count is not met, the tournament is cancelled.
- If the tournament is cancelled, all player buy-ins and the admin guarantee are refunded.
- At the start time, if the minimum is met, round 1 matchmaking is random and the tournament begins immediately.

### Tournament Details / Lobby (Single Page)
The tournament details page is also the lobby and registration page (pre-start) and the live tournament view (post-start).

This page must show:
- Tournament status (upcoming, live, completed, or cancelled).
- Minimum and maximum players.
- Date/time when the tournament begins.
- Buy-in amount (or Free) and any guaranteed prize pool contribution.
- Payouts and prize pool.
- Total time per player.
- Max spend (TNB) per game.

If the user is registered:
- Display their current results and progress.

When the tournament ends:
- Display final results for all players.
- Show trophy graphics next to the top 3 finishers.

Visibility:
- The page is visible to all users.
- All users can view the tournament lobby and watch any tournament game live as spectators.
- Before the tournament begins, non-registered users see a registration view.
- After the tournament begins, non-registered users see the tournament lobby view.
- When a user is actively playing a tournament game, the game page includes a "Back to Tournament Lobby" button (or similar UI) that returns them to the tournament lobby.

### Bracket and Scheduling
The tournament details page must also include the tournament bracket and round schedule.

Tournament format:
- Single-elimination bracket.
- Byes are assigned randomly when the player count is odd.

Bracket and round schedule:
- The bracket is created after registration closes and the minimum player count is met.
- Round schedule times are defined per tournament, for example:
  - Round 1 - 1:00 PM
  - Round 2 - 2:00 PM
  - Finals - 3:00 PM
- A countdown timer shows time until the next round.
- Rounds always start at their scheduled times, even if earlier rounds finish early or run late.

### Match Rules and Ratings
- Tournament matches follow standard Connect Five rules, including special moves and the in-match economy.
- Draws are not allowed in any Connect Five match; if a game ends with no Connect Five, the player who moved first loses.
- Max spend (TNB) per game and total time per player are set by the site admin when creating the tournament.
- Tournament matches affect ELO and player stats the same way as standard matches.
- No rematches in tournament brackets; each pairing is a single game.
- No-shows or disconnects are handled by timeout; the opponent wins by timeout and there is no grace period.
- No tournament-specific leaderboards or badges; results only flow into ELO and match history.

### Time Display
- All tournament times are displayed in the viewer's local time zone.
- Countdown timers are relative and identical for all players.

### Admin Management
An admin section is required so the site admin can create tournaments. Admin creation includes:
- Setting the start time, minimum/maximum players, total time per player, max spend (TNB) per game, and the buy-in amount (or Free).
- Optionally adding a guaranteed amount to the prize pool at creation.
- Defining round schedule times.
- Payouts are always distributed to the top 10% of finishers, weighted by placement, from the total prize pool.
- Selecting which tournament appears in the hero banner (manual selection; no automated logic yet).
- Prize pool funding comes from player buy-ins plus any admin guarantee; all funds are reserved and refunded if the tournament is cancelled.
