import logging

from thenewboston.general.enums import NotificationType
from thenewboston.general.utils.database import apply_on_commit
from thenewboston.notifications.models import Notification

logger = logging.getLogger(__name__)


def notify_challenge(match):
    challenger = match.red
    notification = Notification.objects.create(
        owner_id=match.blue_id,
        payload={
            'notification_type': NotificationType.HEX_CHALLENGE.value,
            'challenger': {
                'id': challenger.id,
                'username': challenger.username,
                'avatar': challenger.avatar.url if challenger.avatar else None,
            },
            'match_id': match.id,
            'board_size': match.board_size,
            'stake_amount': match.stake_amount,
            'time_limit_seconds': match.time_limit_seconds,
        },
    )

    def stream():
        try:
            notification.stream()
        except Exception:
            logger.exception('Could not stream hex challenge %s', match.id)

    apply_on_commit(stream)
