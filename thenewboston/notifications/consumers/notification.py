from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from thenewboston.general.consumers import AuthenticatedUserConsumer

from ..models import Notification


class NotificationConsumer(AuthenticatedUserConsumer):
    def create_notification(self, event):
        """
        Send notification creation details to the client. The event is expected to contain the 'payload' with
        notification details and 'type' indicating the action.
        """
        total_unread_count = Notification.objects.filter(owner_id=self.user_id, is_read=False).count()

        self.send_json(
            {'notification': event['payload'], 'type': event['type'], 'total_unread_count': total_unread_count}
        )

    @staticmethod
    def get_group_name(user_id):
        return f'user_{user_id}_notifications'

    @classmethod
    def stream_notification(cls, *, message_type, notification_data):
        """
        Send notification details to the group associated with the notification owner.
        message_type indicates the type of the action and notification_data contains the notification details.
        """
        channel_layer = get_channel_layer()
        notification_owner_id = notification_data['owner']
        notification_event = {'payload': notification_data, 'type': message_type.value}
        async_to_sync(channel_layer.group_send)(cls.get_group_name(notification_owner_id), notification_event)
