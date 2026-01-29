from asgiref.sync import async_to_sync
from channels.generic.websocket import JsonWebsocketConsumer
from channels.layers import get_channel_layer


class ConnectFiveChatConsumer(JsonWebsocketConsumer):
    def connect(self):
        self.match_id = self.scope['url_route']['kwargs']['match_id']
        self.group_name = self.get_group_name(self.match_id)
        self.accept()
        async_to_sync(get_channel_layer().group_add)(self.group_name, self.channel_name)

    def disconnect(self, close_code):
        async_to_sync(get_channel_layer().group_discard)(self.group_name, self.channel_name)

    @staticmethod
    def get_group_name(match_id):
        return f'connect_five_match_{match_id}_chat'

    @classmethod
    def stream_message(cls, *, message_type, message_data, match_id):
        channel_layer = get_channel_layer()
        event = {'payload': message_data, 'type': message_type.value}
        async_to_sync(channel_layer.group_send)(cls.get_group_name(match_id), event)

    def create_connect_five_chat_message(self, event):
        self.send_json({'chat_message': event['payload'], 'type': event['type']})
