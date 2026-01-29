# Connect Five Game Chat — Business Requirements (Draft)

## Current product context (as of Jan 29, 2026)
- Connect Five has a lobby with personal matches and a public list of active matches for spectating.
- The match page supports spectator mode: non-participants can view the board and match info, but gameplay actions and rematch controls are disabled.
- Match outcomes include Connect 5, full board winner, resign, and timeout. Draws are not part of the rules.
- The match page uses a two-column layout with the board on the left and a right sidebar containing match info, prize pool, spend progress, purchase specials, and resign panels; on smaller screens the sidebar stacks below the board.
- Real-time match updates are already delivered to players and to a public channel used by the lobby; there is no chat data model, API, or UI yet.

## Goals
- Add real-time, match-scoped chat to improve engagement for players and spectators.
- Keep gameplay primary; chat should be helpful but non-blocking.

## Core requirements (MVP)
- One chat room per match, accessible from that match page.
- Chat is available only after a challenge is accepted (i.e., once a match exists).
- Chat remains visible and active after a match ends.
- Authenticated users can view chat content; unauthenticated users cannot access chat.
- Both players and spectators can send messages while viewing a match.
- New messages appear in real time for all participants currently viewing the match.
- Users who open a match mid-game can see recent chat history.
- Messages are text-only and single-line at launch, and each message shows sender identity (username and avatar) plus a timestamp.
- Message ordering is consistent and chronological for all clients.
- Chat UI fits within the existing right sidebar layout and remains usable when the sidebar stacks below the board on smaller screens.
- Chat is always visible (no collapse or separate tab on mobile).
- Messages are stored indefinitely.
- History uses infinite scroll: load the most recent 50 messages by default and load older messages as the user scrolls upward.
- Message rules: max length 280 characters, emojis and links allowed, mentions are not supported.
- No moderation tools, no rate limiting, and no chat-specific notifications for MVP.

## Non-goals for initial release
- Direct private messaging outside of matches.
- Media, file, or GIF uploads.
- Rich text formatting beyond plain text.
- Voice chat or live audio.
- Automated translation.

## Success indicators (optional)
- Percentage of matches with at least one chat message.
- Messages per match (median and percentile).
- Spectator engagement on public matches.

## Open questions
- None.
