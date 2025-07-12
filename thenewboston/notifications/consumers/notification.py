from asgiref.sync import async_to_sync
from channels.generic.websocket import JsonWebsocketConsumer
from channels.layers import get_channel_layer

from ..models import Notification


class NotificationConsumer(JsonWebsocketConsumer):

    def connect(self):
        """
        Accept the incoming connection, retrieve the user ID from the URL route, construct a unique group name, and
        add the client to the group.
        """
        self.user_id = self.scope['url_route']['kwargs']['user_id']
        self.group_name = self.get_group_name(self.user_id)
        self.accept()
        async_to_sync(get_channel_layer().group_add)(self.group_name, self.channel_name)

    def create_notification(self, event):
        """
        Send notification creation details to the client. The event is expected to contain the 'payload' with
        notification details and 'type' indicating the action.
        """
        total_unread_count = Notification.objects.filter(owner_id=self.user_id, is_read=False).count()

        self.send_json({
            'notification': event['payload'],
            'type': event['type'],
            'total_unread_count': total_unread_count,
        })

    def disconnect(self, close_code):
        """Remove the client from the group on disconnection."""
        async_to_sync(get_channel_layer().group_discard)(self.group_name, self.channel_name)

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
