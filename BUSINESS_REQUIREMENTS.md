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
- Active games (including tournament games; tournament games are labeled with a "Tournament" badge)
- Game history (paginated; tournament games are labeled with a "Tournament" badge)
- Time until the user's next tournament game (shown only when the user is registered for an upcoming tournament)
- Tournament info on the dashboard is limited to the user's tournaments (registered, active, completed)
- The user's current ELO

### Tournaments Page (List View)
- Cards for all tournaments (upcoming, live, completed, cancelled); completed tournaments remain visible indefinitely. The list is paginated and not filtered by user participation.
- Each card includes:
  - A small banner image for the tournament.
  - Tournament name.
  - Quick details (example: "Starts Jan 25, 2025 - 2:00 PM EST - 12/16 Players").
  - A single status/CTA area that displays one of the following states:
    - Upcoming: "Register Now", "Full", "Registration opens in 14h 32m", or "Registered" (with a checkmark icon)
    - Live: "Live" (with a "View" CTA)
    - Completed: "Completed" with winner name, finish date/time, and a "View results" CTA
    - Cancelled: "Cancelled"

Clicking a card routes the user to the tournament details page.

### Registration Rules
- Registration opens 1 hour before the tournament start time (fixed for all tournaments).
- Registration closes at the start time (server time); any request at or after start is rejected.
- Users can register or remove their registration until the start time; unregistering refunds the buy-in, and re-registering charges again.
- Buy-ins are deducted and locked at registration.
- Minimum players is configurable per tournament, with an enforced floor of 2.
- If the tournament reaches maximum players before the start time, registration closes and the CTA shows "Full".
- At the start time, if the minimum player count is not met, the tournament is cancelled.
- If the tournament is cancelled, all player buy-ins and the admin guarantee are refunded.
- At the start time, if the minimum is met, round 1 matchmaking is random and the tournament begins immediately.
- Users can register for multiple tournaments even if schedules overlap; missing a match results in a timeout loss.

### Tournament Details / Lobby (Single Page)
The tournament details page is also the lobby and registration page (pre-start) and the live tournament view (post-start).

This page must show:
- Tournament status (upcoming, live, completed, or cancelled).
- Minimum and maximum players.
- Date/time when the tournament begins.
- Buy-in amount (or Free) and any guaranteed prize pool contribution.
- Payouts and prize pool.
- Total time per player.
- Max spend (TNB) per game (fixed at 0; special moves disabled).
- Registered player list (public).

If the user is registered:
- Display their current results and progress.

When the tournament ends:
- Display final results for all players.
- Show trophy graphics next to the top 3 finishers.

Visibility:
- The page is visible to all users.
- All users can view the tournament lobby and watch any tournament game live as spectators.
- Spectators can see both players' remaining time; there is no spectator count or chat.
- Before the tournament begins, non-registered users see a registration view.
- After the tournament begins, non-registered users see the tournament lobby view.
- When a user is actively playing a tournament game, the game page includes a "Back to Tournament Lobby" button (or similar UI) that returns them to the tournament lobby.

### Bracket and Scheduling
The tournament details page must also include the tournament bracket and round schedule.

Tournament format:
- Single-elimination bracket.
- Byes are assigned randomly when the player count is odd and advance the player without a win/loss or ELO change.

Bracket and round schedule:
- The bracket is created after registration closes and the minimum player count is met.
- Round schedule times are defined per tournament, for example:
  - Round 1 - 1:00 PM
  - Round 2 - 2:00 PM
  - Finals - 3:00 PM
- Admin schedule validation enforces a minimum gap between rounds of (2 * total_time_per_player) + buffer (for example, 5 minutes).
- A countdown timer shows time until the next round.
- If a round finishes early, players wait until the scheduled next round; show a "Waiting for next round" state with a countdown.
- Rounds always start at their scheduled times.
- Players may play standard lobby games while waiting between rounds; if they miss their tournament match, they time out.

### Match Rules and Ratings
- Tournament matches follow standard Connect Five rules, but special moves and in-match purchases are disabled.
- Draws are not allowed in any Connect Five match; if a game ends with no Connect Five, the player who moved first loses.
- Max spend (TNB) per game is fixed at 0 for tournaments; total time per player is set by the site admin.
- Tournament matches affect ELO and player stats the same way as standard matches.
- No rematches in tournament brackets; each pairing is a single game.
- No-shows or disconnects are handled by standard per-player timeouts; there is no grace period or reconnect window and the clock keeps running. If both players no-show, the player whose clock runs first times out and loses.
- No tournament-specific leaderboards or badges; results only flow into ELO and match history.

### Time Display
- All tournament times are displayed in the viewer's local time zone.
- Countdown timers are relative and identical for all players.

### Admin Management
An admin section is required so the site admin can create tournaments. Admin creation includes:
- Setting the start time, minimum/maximum players (minimum >= 2), total time per player, and the buy-in amount (or Free).
- Max spend is fixed to 0 for tournaments; special moves are disabled.
- Optionally adding a guaranteed amount to the prize pool at creation.
- Defining round schedule times; validation enforces a minimum gap between rounds of (2 * total_time_per_player) + buffer (for example, 5 minutes).
- Payouts are always distributed to the top 10% of finishers, weighted by placement, from the total prize pool. Paid places = max(1, ceil(total_players * 0.10)); weights are linear by placement (for N paid places, weight = N - place + 1).
- Admins cannot edit tournament settings after creation; to change settings, they must cancel and recreate the tournament.
- Admins can manually cancel a tournament before the start time, triggering full refunds.
- Prize pool funding comes from player buy-ins plus any admin guarantee; all funds are reserved and refunded if the tournament is cancelled.

---
