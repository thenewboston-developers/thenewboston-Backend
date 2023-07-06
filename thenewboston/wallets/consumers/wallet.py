from asgiref.sync import async_to_sync
from channels.generic.websocket import JsonWebsocketConsumer
from channels.layers import get_channel_layer


class WalletConsumer(JsonWebsocketConsumer):

    def connect(self):
        self.user_id = self.scope['url_route']['kwargs']['user_id']
        self.group_name = f'user_{self.user_id}'
        self.accept()
        async_to_sync(get_channel_layer().group_add)(self.group_name, self.channel_name)

    def disconnect(self, close_code):
        async_to_sync(get_channel_layer().group_discard)(self.group_name, self.channel_name)

    @classmethod
    def stream_wallet(cls, *, message_type, wallet_data):
        channel_layer = get_channel_layer()
        wallet_owner_id = wallet_data['owner']
        async_to_sync(channel_layer.group_send)(
            f'user_{wallet_owner_id}',
            {
                'payload': wallet_data,
                'type': message_type.value,
            },
        )

    def update_wallet(self, event):
        self.send_json({
            'type': event['type'],
            'wallet': event['payload'],
        })
