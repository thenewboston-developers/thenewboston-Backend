# Connect Five Chatroom — Business Requirements (Draft)

## Context from the current codebase
- The Connect Five game page renders a right-side sidebar with match-related panels (status, prize pool, spend, purchase, resign). This is the natural location for a chat panel.
- Connect Five match and challenge data are currently only retrievable by the two players involved. There is no spectator access in the game flow today.
- Real-time updates exist for Connect Five matches, but they are player-scoped. There is no existing chat feature or chat data model.

## Business requirements
- Provide a chatroom alongside the Connect Five board, positioned in the right sidebar of the match view.
- The chatroom is scoped to a single match so that messages are visible only to users who join that specific match chat.
- Any authenticated user can join the chatroom for a match, not just the two players.
- Authenticated users can send messages; unauthenticated users cannot access the chatroom.
- Messages should appear in real time for all connected users in that match’s chat.
- The chat should display each message’s author identity in a way consistent with existing user presentation (for example, username and avatar if available).
- Message order should be consistent and stable across clients, and new messages should be appended in a predictable order.
- The chat panel should be usable without disrupting gameplay (scrolling, input focus behavior, and layout fit within the sidebar).
- The chatroom should remain usable on smaller screens where the sidebar stacks under the board.
- Message history should be available when a user joins or refreshes the page, so the chat is not limited to only what is received live.

## Open questions
- Spectator access: Should non-players be allowed to open the match page to reach the chatroom, or should there be a separate chat entry point?
- Read vs write: Do all authenticated users have the same permissions to post, or should spectators be read-only?
- Persistence and retention: How long should match chat messages be stored, and how many messages should be loaded initially?
- Message content rules: Are messages text-only? Are emojis, links, or mentions allowed? What is the max length?
- Moderation: Do we need message deletion, user muting, reporting, or admin moderation tools?
- Match lifecycle: Should chat stay open after a match ends? If so, for how long?
- System messages: Should match events (win, resign, timeout, rematch) appear in the chat feed?
- Notifications: Should chat mentions or new messages trigger notifications elsewhere in the product?
- Rate limits and anti-spam: What throttling or abuse controls are required for high-traffic matches?
- Participant visibility: Should the UI show who is currently in the chat or how many people are connected?
