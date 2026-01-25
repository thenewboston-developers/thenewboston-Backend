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

---

## Open Questions

### Prize Pool & Payouts
1. "Top 10% of finishers, weighted by placement" – what is the exact weighting formula? For example, if 3 players are paid out, what percentage does 1st, 2nd, and 3rd each receive?
2. What happens when 10% results in a fractional number of players (e.g., 12 players = 1.2 players)? Do we round up, round down, or use a minimum of 1?
3. What is the minimum payout threshold? For example, if there are only 5 players, does only 1st place get paid?

> come up with a response to these questions based on what you think we should do

### Round Scheduling & Match Flow
4. What happens if a match is still in progress when the next round is scheduled to start? Does the ongoing match continue until completion, delaying the next round for those players only?
5. If a round finishes early, do players simply wait for the scheduled start time of the next round? Is there any UI indication of this waiting period?
6. Can players participate in non-tournament (standard lobby) games while waiting between tournament rounds?
7. Is there a recommended or enforced minimum buffer time between rounds when admins create the schedule?

### No-Shows & Timeouts
8. The document states no-shows are "handled by timeout" – is this the same timeout as the "total time per player" setting, or is there a separate no-show grace period?
9. What happens if both players fail to show up for a match (double no-show)?
10. If a player disconnects mid-match, is there any reconnection window, or does the clock simply continue running?

### Bye Handling
11. When a bye is assigned (odd number of players), does it count as a win for stats purposes? Does it affect ELO?
12. How is the bye recipient selected? Randomly? Based on seeding/ELO?

### Registration Edge Cases
13. What happens if a user attempts to register at the exact moment the tournament starts (race condition)? Is there a small buffer before the cutoff?
14. Can a user who unregisters re-register if spots are still available?
15. The minimum player count triggers cancellation – what is this minimum? Is it configurable per tournament, or is there a system-wide default?

### Spectating
16. Can spectators see both players' remaining time?
17. Can spectators see special move purchases and the in-match economy?
18. Is there a spectator count displayed on the game or tournament lobby?
19. Will there be any spectator chat or commentary feature?

### Admin Capabilities
20. Can admins edit tournament settings (time, player limits, prize pool, etc.) after creation but before the tournament starts?
21. Can admins manually cancel a tournament before the start time?
22. Can admins view the list of registered players before the tournament begins?
23. What image assets are required for a tournament? (Hero banner dimensions, card thumbnail dimensions, etc.)
24. If no hero tournament is manually selected, what appears in the hero banner area? Is it hidden, or does it default to the next upcoming tournament?

### Tournament History & Archives
25. How long are completed tournaments visible on the Tournaments page?
26. Is there a dedicated "My Tournaments" or tournament history view for users to see their past tournament participation?
27. What does a tournament card display after the tournament is completed? (Winner, final results summary?)

### In-Match Economy (Tournament Games)
28. Does the "max spend (TNB) per game" setting apply independently to each tournament game, or is there a cumulative limit across all games in the tournament?
29. When players spend TNB on special moves during tournament games, where does that TNB go? Into the prize pool, or is it handled the same as standard matches?

### Miscellaneous
30. Are tournament games visually distinguished from standard games in the "Active games" and "Game history" sections of the Dashboard?
31. Can a user be registered for multiple tournaments that have overlapping schedules?
32. What happens if a registered user's TNB balance drops below the buy-in amount before the tournament starts (e.g., due to other transactions)?
