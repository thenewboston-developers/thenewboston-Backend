import logging

from asgiref.sync import async_to_sync
from channels.generic.websocket import JsonWebsocketConsumer
from channels.layers import get_channel_layer

from thenewboston.ia.models import Conversation

logger = logging.getLogger(__name__)


class MessageConsumer(JsonWebsocketConsumer):

    def connect(self):
        """
        Accept the incoming connection, retrieve the user ID from the URL route, construct a unique group name, and
        add the client to the group.
        """
        self.user_id = self.scope['url_route']['kwargs']['user_id']
        self.group_name = self.get_group_name(self.user_id)
        self.accept()
        async_to_sync(get_channel_layer().group_add)(self.group_name, self.channel_name)

    def create_message(self, event):
        """
        Send message creation details to the client. The event is expected to contain the 'payload' with message
        details and 'type' indicating the action.
        """

        logger.warning('456')
        logger.warning(event)

        self.send_json({
            'message': event['payload'],
            'type': event['type'],
        })

    def disconnect(self, close_code):
        """Remove the client from the group on disconnection."""
        logger.warning('client disconnecting')
        async_to_sync(get_channel_layer().group_discard)(self.group_name, self.channel_name)

    @staticmethod
    def get_group_name(user_id):
        return f'user_{user_id}_messages'

    @classmethod
    def stream_message(cls, *, message_type, message_data):
        """
        Send message details to the group associated with the conversation owner.
        message_type indicates the type of the action and message_data contains the message details.
        """
        channel_layer = get_channel_layer()
        conversation = Conversation.objects.get(pk=message_data['conversation'])
        conversation_owner_id = conversation.owner.id

        message_event = {
            'payload': message_data,
            'type': message_type.value,
        }

        logger.warning(cls.get_group_name(conversation_owner_id))
        logger.warning(message_event)

        async_to_sync(channel_layer.group_send)(cls.get_group_name(conversation_owner_id), message_event)
