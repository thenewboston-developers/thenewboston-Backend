import logging

from thenewboston.general.enums import NotificationType
from thenewboston.general.utils.database import apply_on_commit
from thenewboston.notifications.models import Notification

logger = logging.getLogger(__name__)


def notify_challenge(match):
    challenger = match.host
    notification = Notification.objects.create(
        owner_id=match.guest_id,
        payload={
            'notification_type': NotificationType.MANCALA_CHALLENGE.value,
            'challenger': {
                'id': challenger.id,
                'username': challenger.username,
                'avatar': challenger.avatar.url if challenger.avatar else None,
            },
            'match_id': match.id,
            'stake_amount': match.stake_amount,
            'time_limit_seconds': match.time_limit_seconds,
        },
    )

    def stream():
        try:
            notification.stream()
        except Exception:
            # The challenge is committed; the opponent still finds it in the lobby.
            logger.exception('Could not stream mancala challenge %s', match.id)

    apply_on_commit(stream)
