# Connect Five: Business Requirements

## Current Functionality Review (Connect Five)
- Navigation currently includes a Lobby and a Leaderboard for Connect Five.
- Lobby (current homepage) supports direct player challenges:
  - Challenge creation includes opponent selection, stake amount (TNB), max spend (TNB), and total time per player.
  - Incoming and outgoing challenges are listed separately; challenges can be accepted, declined, or cancelled.
  - Challenges expire if not accepted within a short window.
- Matches:
  - Active games and game history are shown in separate lists; history is paginated.
  - Matches can end by Connect Five, timeout, or draw; a winner is recorded when applicable.
  - Rematches are supported after completed games.
- Gameplay rules and economy:
  - Standard Connect Five on a 15x15 board.
  - Players can purchase special move types using TNB during a match (horizontal two, vertical two, bomb).
  - Each match has a max spend limit per player and a total time per player.
  - Prize pools are funded by stakes and in-game purchases; winner takes the pool; draws refund contributions.
- ELO and leaderboard:
  - Each user has an ELO rating and win/loss/draw stats.
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
    - "Registration opens in 14h 32m" (countdown until registration opens)
    - "Registered" (with a checkmark icon)

Clicking a card routes the user to the tournament details page.

### Registration Rules
- Registration opens 1 hour before the tournament start time.
- Registration closes at the start time.
- Users can register or remove their registration until the start time.
- At the start time, if the minimum player count is not met, the tournament is cancelled.
- At the start time, if the minimum is met, round 1 matchmaking is random and the tournament begins immediately.

### Tournament Details / Lobby (Single Page)
The tournament details page is also the lobby and registration page (pre-start) and the live tournament view (post-start).

This page must show:
- Tournament status (upcoming, live, completed, or cancelled).
- Minimum and maximum players.
- Date/time when the tournament begins.
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
- Before the tournament begins, non-registered users see a registration view.
- After the tournament begins, non-registered users see the tournament lobby view.

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

### Match Rules and Ratings
- Tournament matches follow standard Connect Five rules, including special moves and the in-match economy.
- Max spend (TNB) per game and total time per player are set by the site admin when creating the tournament.
- Tournament matches affect ELO and player stats the same way as standard matches.
- No-shows or disconnects are handled by timeout; the opponent wins by timeout.

### Time Display
- All tournament times are displayed in the viewer's local time zone.
- Countdown timers are relative and identical for all players.

### Admin Management
An admin section is required so the site admin can create tournaments. Admin creation includes:
- Setting the start time, minimum/maximum players, total time per player, and max spend (TNB) per game.
- Defining round schedule times.
- Defining payout distribution (for example: 1st = 300 TNB, 2nd = 200 TNB, 3rd = 100 TNB).
- Selecting which tournament appears in the hero banner (manual selection; no automated logic yet).
- Funding the prize pool from the admin wallet at creation; funds are reserved and refunded if the tournament is cancelled.

## Remaining Questions
- None at this time.
