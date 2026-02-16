# Post Comments Mini-Chat Business Requirements

Prepared on February 16, 2026

## 1. Purpose
Define the business requirements to evolve post comments from a partially expanded comment list into a mini-chat experience, while preserving current product behaviors users already rely on (comment creation, mentions, tips, and notification-driven updates).

## 2. Product Goal
Make post conversations feel live, continuous, and easier to follow, similar to Slack/Discord-style chat flow, without losing existing social and wallet-related comment features.

## 3. Current-State Summary (Deep-Dive Findings)

### 3.1 Where comments appear
- Comments are shown inside each post card/panel across Feed, Profile posts, and Post Detail views.
- Users can hide/show the comment section via the post-level comment toggle.

### 3.2 Current comment section structure
- The composer (`Add a comment`, emoji picker, tip controls, send) appears above the visible comment list.
- Only an initial subset of comments is shown at first.
- Users load more comments manually via a clickable `Show X more comments` control.

### 3.3 Current visual style
- Comment cards use a light gray background style (`#f3f4f7` palette family).
- Vertical spacing between comment items is relatively loose.

### 3.4 Existing real-time and update behavior
- New comments can appear in-session from:
  - the authenticated user posting a comment,
  - real-time notifications (for users who receive comment-related notifications),
  - post data refresh/reload flows.
- Updated comments and deleted comments are not currently broadcast to all viewers in real time in a unified way.
- Real-time comment updates are currently tied mainly to notification scenarios, not a dedicated per-post live comment stream.

### 3.5 Existing business behaviors to preserve
- Mentions in comments.
- Optional tipping from commenter to post owner via comment.
- Emoji insertion in comment composer.
- Comment edit/delete permissions and flows.
- Notification generation and notification center behavior.

## 4. Target Experience (To-Be)

### 4.1 Conversation layout
- Remove the `Show X more comments` interaction entirely.
- Keep comments visible by default, with ability to hide/show using the existing post-level comment toggle.
- Move the full comment composer to the bottom of the post panel.
- Display the comment history in a dedicated area directly above the composer.
- The comment history area must have a maximum height and vertical scrolling when content exceeds that height.
- Comment pane max-height targets:
  - desktop: 300px,
  - mobile: 220px.
- Composer layout at the bottom must be:
  - comment textarea first,
  - controls row below textarea,
  - emoji and tip controls aligned bottom-left on that row,
  - live-connection indicator light displayed on that same bottom row,
  - send button aligned bottom-right on that row.

### 4.2 Visual direction
- Remove the existing `#f3f4f7` style treatment from comment items.
- Reduce spacing between comments so the thread feels denser and more chat-like.
- Overall tone should align more closely with Slack/Discord conversation rhythm: compact, readable, continuous.

### 4.3 Real-time behavior trigger
- When a user places their cursor in the `Add a comment` input, the client must connect to a new live backend comment channel for that post conversation.
- When input focus is lost, the live comment channel connection closes immediately.
- A small connection indicator light must be visible in the composer bottom row for the post comment live channel.
- When the user focuses/clicks into the comment textarea, show a status label to the right of the light.
- Status model for the light + label:
  - gray + `Disconnected` (default state),
  - green + `Connected`,
  - red + `Error` (websocket connection failed),
  - blue + `Syncing` (briefly shown right after websocket connects, while the client runs the post-sync comment fetch).
- That live channel must deliver all comment lifecycle events relevant to that post:
  - new comments,
  - edited/updated comments,
  - deleted comments.
- Immediately after the channel connects, the client must fetch the latest comments for that post to resync state and close any gap between:
  - when the post was first loaded on screen, and
  - when the user activated live listening by focusing the composer.

### 4.4 Coexistence with current update paths
- The new live comment stream must work cleanly with existing update mechanisms that already modify comments:
  - incoming notification-based comment updates,
  - local authenticated-user comment creation via standard submit flow.
- Live comment websocket updates are delivered to any client currently connected to that post conversation.
- Users must not see broken state, missing comments, stale edits, or duplicate comment rows when multiple update paths fire around the same time.

## 5. Functional Business Requirements

### 5.1 Composer requirements
- Composer remains feature-complete:
  - text entry via textarea,
  - emoji selection,
  - tip currency + amount controls,
  - send action.
- Composer location is fixed to the bottom of the comment section within the post panel (not replacing the existing post body/actions area).
- Composer textarea behavior:
  - supports multi-line entry,
  - grows with content up to 4 visible rows,
  - once content exceeds 4 rows, textarea stays capped and shows vertical scroll.
- Enter behavior:
  - Shift + Enter creates a new line,
  - regular Enter behavior for submit should remain aligned with existing product expectations.

### 5.2 Comment list requirements
- The full available conversation for the post is accessible through scrolling.
- No manual pagination or “load more comments” button is shown.
- Comments must be ordered oldest-to-newest (newest at bottom), uniformly across all screens.

### 5.3 Live update requirements
- New comment events must appear in the thread in near real time.
- Edit events must update the existing comment item in place.
- Delete events must remove the comment entirely from the thread.
- Edited comments do not show any additional “edited” UI indicator.
- Thread auto-scroll to newest comment occurs only when the user is already near the bottom of the comment pane.

### 5.4 Data consistency requirements
- If the same comment change is received through multiple channels, the UI should resolve to a single correct state.
- Local actions by the authenticated user and remote events from other users must converge without requiring page refresh.
- If the same comment arrives through both notification flow and live-comment flow, both updates are accepted and the last-arriving payload in Redux wins (no advanced conflict resolution).

### 5.5 Surface consistency requirements
- The mini-chat behavior should be consistent wherever the post component is used:
  - Feed,
  - Profile post list,
  - Post detail opened from notifications.

### 5.6 Backward-compatible social behaviors
- Mention and tip behavior in comments must remain intact.
- Existing notification workflows remain valid and continue to function for users who rely on the notifications page.
- No additional moderation/visibility business rules are introduced as part of this mini-chat change.

## 6. Quality and UX Expectations
- Conversation should feel immediate and reliable during active participation.
- Thread density should improve readability without becoming visually cluttered.
- Scrolling behavior should remain stable as new comments arrive.
- Experience should remain usable on desktop and mobile.

## 7. Acceptance Criteria (Business-Level)
- Users can no longer see or click any `Show X more comments` UI.
- In every post, comments are visible by default and can still be collapsed via the existing toggle.
- In every post, comment input controls are located at the bottom of the comment section.
- The comments area scrolls vertically when long, instead of expanding indefinitely.
- The comments pane max-height is 300px on desktop and 220px on mobile.
- Comment visuals are compact and no longer use the previous gray bubble treatment.
- While actively typing/focused in comment input, users receive live new/edit/delete comment updates for that post.
- When comment input loses focus, that post’s live comment channel disconnects immediately.
- A connection status light is visible and correctly reflects channel state (green connected, gray disconnected).
- The connection indicator appears in the composer bottom row.
- When the user focuses the textarea, the status text appears to the right of the light and correctly maps:
  - gray + `Disconnected` (default),
  - green + `Connected`,
  - red + `Error`,
  - blue + `Syncing` (briefly during post-connect sync fetch).
- Right after live channel connection, the system performs a post-specific comment refresh to sync latest comments.
- Live updates do not conflict with existing notification updates or user submit flows.
- No visible duplication or contradictory states appear in active conversations.
- Any user connected to a post’s live channel receives that post’s live comment events.
- Bottom composer layout is:
  - textarea on top,
  - emoji + tip controls bottom-left,
  - send button bottom-right.
- Textarea expands with content up to 4 rows and then enables internal vertical scrolling.
- Comments are displayed oldest-to-newest (newest at bottom) across all screens.
- Deleted comments disappear from the thread instead of showing placeholders.
- No edited badge/indicator is shown for updated comments.
- Auto-scroll to newest happens only when user is already near bottom.
- Dual-path updates (notification + live channel) follow last-write-wins behavior in Redux.

## 8. Out of Scope for This Change
- Major redesign of the full post card outside the comment section.
- Introducing brand-new social features (threaded replies, reactions-to-comments, typing indicators, read receipts).
- Changing notification center information architecture.
