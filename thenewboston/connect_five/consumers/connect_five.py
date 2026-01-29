from asgiref.sync import async_to_sync
from channels.generic.websocket import JsonWebsocketConsumer
from channels.layers import get_channel_layer


class ConnectFiveConsumer(JsonWebsocketConsumer):
    def connect(self):
        """
        Accept the incoming connection, retrieve the user ID from the URL route, construct a unique group name, and
        add the client to the group.
        """
        self.user_id = self.scope['url_route']['kwargs']['user_id']
        self.group_name = self.get_group_name(self.user_id)
        self.accept()
        async_to_sync(get_channel_layer().group_add)(self.group_name, self.channel_name)

    def disconnect(self, close_code):
        """Remove the client from the group on disconnection."""
        async_to_sync(get_channel_layer().group_discard)(self.group_name, self.channel_name)

    @staticmethod
    def get_group_name(user_id):
        return f'user_{user_id}_connect_five'

    @classmethod
    def stream_challenge(cls, *, message_type, challenge_data, user_ids):
        """
        Send challenge updates to all user groups involved in the challenge.
        message_type indicates the type of the action and challenge_data contains the serialized challenge.
        """
        cls.stream_to_users(message_type=message_type, payload=challenge_data, user_ids=user_ids)

    @classmethod
    def stream_match(cls, *, message_type, match_data, user_ids):
        """
        Send match updates to all user groups involved in the match.
        message_type indicates the type of the action and match_data contains the serialized match.
        """
        cls.stream_to_users(message_type=message_type, payload=match_data, user_ids=user_ids)

    @classmethod
    def stream_to_users(cls, *, message_type, payload, user_ids):
        channel_layer = get_channel_layer()
        event = {'payload': payload, 'type': message_type.value}
        for user_id in set(user_ids):
            async_to_sync(channel_layer.group_send)(cls.get_group_name(user_id), event)

    def update_connect_five_challenge(self, event):
        """
        Send challenge update details to the client. The event is expected to contain the serialized challenge
        payload and 'type' indicating the action.
        """
        self.send_json({'challenge': event['payload'], 'type': event['type']})

    def update_connect_five_match(self, event):
        """
        Send match update details to the client. The event is expected to contain the serialized match payload and
        'type' indicating the action.
        """
        self.send_json({'match': event['payload'], 'type': event['type']})


class ConnectFivePublicConsumer(JsonWebsocketConsumer):
    group_name = 'connect_five_public'

    def connect(self):
        self.accept()
        async_to_sync(get_channel_layer().group_add)(self.group_name, self.channel_name)

    def disconnect(self, close_code):
        async_to_sync(get_channel_layer().group_discard)(self.group_name, self.channel_name)

    @classmethod
    def stream_match(cls, *, message_type, match_data):
        channel_layer = get_channel_layer()
        event = {'payload': match_data, 'type': message_type.value}
        async_to_sync(channel_layer.group_send)(cls.group_name, event)

    def update_connect_five_match(self, event):
        self.send_json({'match': event['payload'], 'type': event['type']})
