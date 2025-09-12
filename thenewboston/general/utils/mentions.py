import re
from typing import List, Set

from django.contrib.auth import get_user_model
from django.db.models import Q

User = get_user_model()

# Regex pattern to match @username mentions
# Matches @username where username can contain letters, numbers, underscores
# Must be preceded by whitespace or start of string
# Must be followed by whitespace, punctuation, or end of string
MENTION_PATTERN = re.compile(r'(?:^|(?<=\s))@([a-zA-Z0-9_]+)(?=\s|[.,!?;:\'\"]|$)', re.MULTILINE)


def extract_mentions(text: str) -> Set[str]:
    """
    Extract unique usernames from @mentions in text.

    Args:
        text: The text content to search for mentions

    Returns:
        Set of unique usernames (without @ prefix)
    """
    if not text:
        return set()

    matches = MENTION_PATTERN.findall(text)
    return set(matches)


def validate_mentions(usernames: Set[str]) -> List[User]:
    """
    Validate mentioned usernames and return existing users.

    Args:
        usernames: Set of usernames to validate

    Returns:
        List of User objects that exist in the database
    """
    if not usernames:
        return []

    # Case-insensitive lookup for usernames
    # Using Q objects for better query optimization
    queries = Q()
    for username in usernames:
        queries |= Q(username__iexact=username)

    return list(User.objects.filter(queries).only('id', 'username'))


def get_mentioned_users(text: str) -> List[User]:
    """
    Extract mentions from text and return valid User objects.

    Args:
        text: The text content to search for mentions

    Returns:
        List of User objects that were mentioned
    """
    usernames = extract_mentions(text)
    return validate_mentions(usernames)


def replace_mentions_with_links(text: str, link_format: str = '<a href="/users/{user_id}">@{username}</a>') -> str:
    """
    Replace @mentions in text with HTML links.

    Args:
        text: The text content with mentions
        link_format: Format string for the link (must have {user_id} and {username} placeholders)

    Returns:
        Text with mentions replaced by links
    """
    if not text:
        return text

    mentioned_usernames = extract_mentions(text)
    if not mentioned_usernames:
        return text

    users = validate_mentions(mentioned_usernames)
    user_map = {user.username.lower(): user for user in users}

    def replace_mention(match):
        username = match.group(1)
        user = user_map.get(username.lower())
        if user:
            return link_format.format(user_id=user.id, username=user.username)
        return match.group(0)  # Keep original if user not found

    return MENTION_PATTERN.sub(replace_mention, text)


def create_mention_notifications(
    mentioned_users: List[User], mentioner: User, content_type: str, content_id: int
) -> None:
    """
    Create notifications for mentioned users.

    Args:
        mentioned_users: List of users who were mentioned
        mentioner: The user who created the mention
        content_type: Type of content ('post' or 'comment')
        content_id: ID of the post or comment
    """
    from thenewboston.notifications.models import Notification

    notifications = []
    for user in mentioned_users:
        # Don't notify users of their own mentions
        if user.id == mentioner.id:
            continue

        notification = Notification(
            owner=user,
            payload={
                'type': 'mention',
                'content_type': content_type,
                'content_id': content_id,
                'mentioner_id': mentioner.id,
                'mentioner_username': mentioner.username,
                'mentioner_avatar': mentioner.avatar.url if mentioner.avatar else None,
            },
        )
        notifications.append(notification)

    if notifications:
        Notification.objects.bulk_create(notifications)
        # Stream notifications to WebSocket
        for notification in notifications:
            notification.stream()
