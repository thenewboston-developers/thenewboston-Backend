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
- Time until the next tournament game for the user
- The user’s ELO summary, including:
  - Current ELO
  - A chart showing ELO over time

### Tournaments Page (List View)
At the top of the page:
- A large hero banner highlighting the next major upcoming tournament

Below the hero:
- Cards for each upcoming tournament
- Each card includes:
  - A small banner image for the tournament
  - Tournament name
  - Quick details (example: “Starts Jan 25, 2025 • 2:00 PM EST - 12/16 Players”)
  - A single call-to-action button that displays one of the following states:
    - “Register Now”
    - “Registration opens in 14h 32m” (countdown)
    - “Registered” (with a checkmark icon)

Clicking a card routes the user to the tournament details page.

### Tournament Details / Lobby (Single Page)
The tournament details page is also the lobby and registration page (pre-start) and the live tournament view (post-start).

This page must show:
- Tournament status (e.g., upcoming, completed, or “Live - Round 2 In Progress”)
- Minimum and maximum players
- Date/time when the tournament begins
- Payouts and prize pool
- Total time per player
- Max spend (TNB) per game

If the user is registered:
- Display their current results and progress

When the tournament ends:
- Display final results for all players
- Show trophy graphics next to the top 3 finishers

### Bracket and Scheduling
The tournament details page must also include the tournament bracket and round schedule.

Tournament flow:
1. Registration
2. Random matchmaking for round 1
3. Bracket creation and round schedule after registration, for example:
   - Round 1 - 1:00 PM
   - Round 2 - 2:00 PM
   - Finals - 3:00 PM

Additional requirements:
- Users can register and remove their registration before the tournament begins.
- A countdown timer shows time until the next round.

### Admin Management
An admin section is required so the site admin can create tournaments.

## Open Questions
- How is the “next major upcoming tournament” chosen for the hero banner (manual flag, prize pool size, start time, etc.)?
- What are the registration open/close rules (open at publish time, close at start time, or earlier)?
- What happens if the minimum player count is not met by the start time (cancel, delay, reschedule, auto-start with fewer players)?
- What is the tournament format (single elimination, double elimination, Swiss, round robin)? How are byes handled for odd player counts?
- Are tournament matches subject to the same rules as standard matches (special moves, max spend, time controls)?
- Do tournament matches affect ELO and player stats? If yes, is the ELO impact the same as standard matches?
- How is the prize pool funded (entry fees, sponsor pool, both)? What is the payout distribution model?
- What is the behavior for no-shows or disconnects (forfeit rules, grace periods, auto-advancement)?
- How should the “next tournament game” on the dashboard behave for users not registered in any tournament?
- What time zone should be used for all tournament times and countdowns?
- Should tournament pages be visible to non-registered users, and if so, what actions are available?
- Is there a requirement to store and display historical ELO trend data (time range, granularity, and retention)?
