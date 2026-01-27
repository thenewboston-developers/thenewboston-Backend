# Connect 5 Game Chat Feature - Business Requirements

## Overview

Add a real-time chat feature to Connect 5 games that allows the two players and any authenticated spectators to communicate during a match. The chat will appear to the right of the game board, functioning as a mini chatroom tied to each specific match.

---

## Core Requirements

### 1. Chat Participants

- **Players**: Both player_a and player_b of the match can send and receive messages
- **Spectators**: Any authenticated user can join the chat and participate, even if they are not playing
- **Anonymous users**: Unauthenticated users cannot participate in chat (view-only or no access)

### 2. Chat Scope

- Each chat room is tied to a specific match (one chat per match)
- Messages are associated with the match they were sent in
- Chat is accessible from the game page

### 3. Real-Time Messaging

- Messages appear instantly for all participants without page refresh
- Uses existing WebSocket infrastructure
- New participants joining mid-game see chat history

### 4. Message Content

- Text-based messages
- Display sender's username and avatar
- Display timestamp for each message
- Messages should support basic text (no rich formatting required initially)

### 5. User Interface Placement

- Chat panel located to the right of the game board
- Should not obstruct the game board or critical game controls
- Chat input field at the bottom of the chat panel
- Scrollable message history above the input

---

## Open Questions

### Participant Access

1. **Spectator discovery**: How do spectators find/join a game's chat? Do we need a "spectate" feature where users can browse active matches, or do they need a direct link?

2. **Participant limit**: Should there be a maximum number of spectators allowed in a single game's chat?

3. **Player-only mode**: Should players have the option to disable spectator chat and make it players-only?

### Chat Lifecycle

4. **Pre-match chat**: Should chat be available before the match starts (e.g., during challenge acceptance)?

5. **Post-match persistence**: What happens to the chat when the match ends?
   - Does the chat room close immediately?
   - Can players continue chatting after the game finishes?
   - Is there a grace period (e.g., 5-10 minutes after match ends)?

6. **Rematch continuity**: If players start a rematch, should chat history carry over to the new match or start fresh?

7. **Chat history retention**: How long should chat messages be stored in the database? Indefinitely, or purged after a certain period?

### Message Handling

8. **Character limit**: What should the maximum message length be? (Suggested: 280-500 characters)

9. **Rate limiting**: Should we limit how many messages a user can send per minute to prevent spam?

10. **Message editing/deletion**: Can users edit or delete their own messages after sending?

11. **Empty messages**: Should we allow messages with only whitespace or emojis?

### Moderation & Safety

12. **Content filtering**: Should messages be filtered for profanity or inappropriate content?

13. **Reporting**: Should users be able to report inappropriate messages or users?

14. **Blocking**: If a user has blocked another user (if such a feature exists), should they still see each other's messages in game chat?

15. **Muting**: Can players mute the chat entirely if they find it distracting during gameplay?

16. **Admin moderation**: Do admins/moderators need the ability to delete messages or ban users from chat?

### Notifications

17. **Unread indicators**: Should there be a notification badge for new messages when the chat is collapsed or the user is scrolled up?

18. **Sound notifications**: Should new messages trigger a sound alert? If so, should it be toggleable?

19. **Desktop notifications**: Should chat messages trigger browser notifications when the user is on a different tab?

### User Experience

20. **Mobile layout**: How should the chat appear on mobile devices where screen space is limited?
    - Collapsible panel?
    - Separate tab/view?
    - Hidden by default?

21. **Distinguishing participants**: Should players be visually distinguished from spectators in the chat (e.g., special badge, different color)?

22. **System messages**: Should the chat display system messages for game events (e.g., "Player X made a move", "Player Y purchased a BOMB")?

23. **Quick chat/emotes**: Should there be predefined quick messages or emoji reactions for faster communication during timed games?

### Data & Privacy

24. **Chat visibility**: Can anyone view the chat history of a completed match, or only participants?

25. **Export**: Should users be able to export or download their chat history?

---

## Assumptions (To Be Confirmed)

1. Chat will use the existing WebSocket infrastructure (Django Channels)
2. Messages will be persisted in the database
3. Authentication is required to send messages
4. The feature is text-only at launch (no image/file uploads)
5. All chat participants see the same messages (no private messaging within game chat)

---

## Out of Scope (For Initial Release)

These features may be considered for future iterations:

- Direct private messaging between users outside of games
- Rich text formatting (bold, italic, links)
- Image/GIF/file sharing in chat
- Message reactions (like/dislike)
- Chat translation for international users
- Voice chat integration
- Chat replays synchronized with game replays

---

## Dependencies

- Existing Connect 5 match system
- User authentication system
- WebSocket infrastructure (Django Channels)
- Frontend game page layout

---

## Success Metrics (Suggested)

Consider tracking:
- Number of messages sent per match
- Percentage of matches with chat activity
- Average spectator count per match
- User engagement before/after chat feature launch
- Report/moderation volume
