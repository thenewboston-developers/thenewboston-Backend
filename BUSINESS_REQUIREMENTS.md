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
- Active games (including tournament games; tournament games are labeled with a "Tournament" badge plus tournament name and round label)
- Game history (paginated; tournament games show the "Tournament" badge plus tournament name and round label)
- Upcoming tournament times:
  - For each registered upcoming tournament, show time until it starts.
  - For active tournaments, show time until the user's next round.
  - Multiple entries may appear when the user is registered for multiple tournaments.
- Tournament info on the dashboard is limited to the user's tournaments (registered, active, completed)
- If a user is eliminated from an active tournament, that tournament moves into their completed list even while the tournament is still live.
- The user's current ELO

### Tournaments Page (List View)
- Cards for all tournaments (live, upcoming, completed), ordered live then upcoming then completed; completed tournaments remain visible indefinitely. The list is paginated and not filtered by user participation.
- Cancelled tournaments are not visible anywhere in the user UI.
- The list view requires sign-in; signed-out users are prompted to sign in.
- Each card includes:
  - A small banner image for the tournament.
  - Tournament name.
  - Quick details (example: "Starts Jan 25, 2025 - 2:00 PM EST - 12/16 Players").
  - A single status/CTA area that displays one of the following states:
    - Upcoming: "Register Now", "Full", "Registration opens in 14h 32m", or "Registered" (with a checkmark icon)
    - Live: "Live" (with a "View" CTA)
    - Completed: "Completed" with winner name, finish date/time, and a "View results" CTA
  - If the user is registered, the CTA shows "Registered" (with a checkmark icon) even when the tournament is full.

Clicking a card routes the user to the tournament details page.

### Registration Rules
- Registration opens 1 hour before the tournament start time (fixed for all tournaments).
- Registration closes at the start time (server time); any request at or after start is rejected.
- Users can register or remove their registration until the start time; unregistering refunds the buy-in, and re-registering charges again.
- Buy-ins are deducted and locked at registration.
- Buy-ins are TNB only; free tournaments still include a guaranteed TNB prize pool.
- Users without a TNB wallet can register for free tournaments; if they win, a TNB wallet is created for payout.
- Minimum players is configurable per tournament, with an enforced floor of 2.
- If the tournament reaches maximum players before the start time, registration closes and the CTA shows "Full". If a spot opens before the start time, registration reopens.
- At the start time, if the minimum player count is not met, the tournament is cancelled.
- If the tournament is cancelled, all player buy-ins and the admin guarantee are refunded.
- Registered users receive a notification when a tournament is cancelled.
- At the start time, if the minimum is met, round 1 matchmaking is random and the tournament begins immediately.
- Users can register for multiple tournaments even if schedules overlap; missing a match results in a timeout loss. No warnings or blocks are shown for overlaps.

### Tournament Details / Lobby (Single Page)
The tournament details page is also the lobby and registration page (pre-start) and the live tournament view (post-start).

This page must show:
- Tournament status (upcoming, live, or completed).
- Minimum and maximum players.
- Date/time when the tournament begins.
- Buy-in amount (or Free) and any guaranteed prize pool contribution.
- Payouts and prize pool (guaranteed minimum and current totals based on registered players; winner takes all).
- Total time per player.
- Max spend (TNB) per game (fixed at 0; special moves disabled).
- Registered player list (avatar, username, current ELO).

If the user is registered:
- Display their wins/losses, current round, and next opponent.

When the tournament ends:
- Display final results for all players, including placement and elimination round.
- Highlight the winner with a trophy graphic.

Visibility:
- The page requires sign-in; unauthenticated users are prompted to sign in.
- Signed-in users can view the tournament lobby and watch any tournament game live as spectators.
- Spectators can see both players' remaining time; there is no spectator count or chat.
- Before the tournament begins, signed-in non-registered users see a registration view.
- If registration is not yet open, the registration view shows a disabled register CTA with a countdown.
- After the tournament begins, signed-in non-registered users see the tournament lobby view.
- If a signed-in user has an active tournament match, the lobby shows a "Return to Game" button; clicking their matchup in the bracket also opens the game.
- When a user is actively playing a tournament game, the game page includes a "Back to Tournament Lobby" button (or similar UI) that returns them to the tournament lobby.
- If a user opens a cancelled tournament (for example, via a direct link), show a cancellation message.

### Bracket and Scheduling
The tournament details page must also include the tournament bracket and round schedule.

Tournament format:
- Single-elimination bracket.
- Byes are assigned randomly when the player count is odd and advance the player without a win/loss or ELO change.
- Byes do not create match records and do not appear in match history; they are only shown as bracket advancement.

Bracket and round schedule:
- The bracket is created after registration closes and the minimum player count is met.
- The number of rounds is based on the player count.
- The admin sets a tournament start time and a break time between rounds; per-round start times are derived automatically.
- Round 1 starts at the tournament start time.
- Each round length equals the max possible game duration (2 * total_time_per_player) plus the configured break time.
- A countdown timer shows time until the next round.
- If a round finishes early, players wait until the scheduled next round; show a "Waiting for next round" state with a countdown.
- Rounds always start at their scheduled times, even if all matches finish early.
- Players may play standard lobby games while waiting between rounds; if they miss their tournament match, they time out.

### Match Rules and Ratings
- Tournament matches follow standard Connect Five rules, but special moves and in-match purchases are disabled.
- Tournament game UI hides spend/purchase elements and any result TNB delta callouts.
- Draws are not allowed in any Connect Five match; if a game ends with no Connect Five, the player who moved first loses. Existing draw results should be cleaned up before tournament work begins.
- Max spend (TNB) per game is fixed at 0 for tournaments; total time per player is set by the site admin.
- The starting player for each tournament match is random.
- Tournament matches affect ELO and player stats the same way as standard matches.
- No rematches in tournament brackets; each pairing is a single game.
- No-shows or disconnects are handled by standard per-player timeouts; there is no grace period or reconnect window and the clock keeps running. If both players no-show, the player whose clock runs first times out and loses.
- No tournament-specific leaderboards or badges; results only flow into ELO and match history.

### Time Display
- All tournament times are displayed in the viewer's local time zone.
- Countdown timers are relative and identical for all players.

### Admin Management
An admin section is required so the site admin can create tournaments. Admin creation includes:
- Setting the start time, minimum/maximum players (minimum >= 2), total time per player, buy-in amount (or Free), and break time between rounds.
- Providing a banner image (required).
- Max spend is fixed to 0 for tournaments; special moves are disabled.
- Optionally adding a guaranteed amount to the prize pool at creation (including for free tournaments).
- Round schedule times are generated automatically based on start time, total time per player, and break time.
- The winner receives the entire prize pool; no other payouts are made.
- Admins cannot edit tournament settings after creation; to change settings, they must cancel and recreate the tournament.
- Admins can manually cancel a tournament before the start time, triggering full refunds.
- Admins cannot cancel a tournament after it has started.
- Prize pool funding comes from player buy-ins plus any admin guarantee; all funds are reserved and refunded if the tournament is cancelled.

---
