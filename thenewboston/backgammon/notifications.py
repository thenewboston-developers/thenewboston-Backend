from thenewboston.general.enums import NotificationType
from thenewboston.notifications.models import Notification


def notify_challenge(match):
    if match.mode != 'human':
        return
    challenger = match.white
    Notification(
        owner_id=match.black_id,
        payload={
            'notification_type': NotificationType.BACKGAMMON_CHALLENGE.value,
            'challenger': {
                'id': challenger.id,
                'username': challenger.username,
                'avatar': challenger.avatar.url if challenger.avatar else None,
            },
            'match_id': match.id,
            'stake_amount': match.stake_amount,
            'target_score': match.target_score,
            'time_limit_seconds': match.time_limit_seconds,
        },
    ).save(should_stream=True)
