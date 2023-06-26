from asgiref.sync import async_to_sync
from channels.generic.websocket import JsonWebsocketConsumer
from channels.layers import get_channel_layer


class OrderJsonWebsocketConsumer(JsonWebsocketConsumer):

    def connect(self):
        self.accept()
        async_to_sync(get_channel_layer().group_add)('orders', self.channel_name)

    def create_order(self, event):
        self.send_json({
            'order': event['payload'],
            'type': event['type'],
        })

    def disconnect(self, close_code):
        async_to_sync(get_channel_layer().group_discard)('orders', self.channel_name)

    @classmethod
    def send_order_data(cls, *, message_type, order_data):
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            'orders',
            {
                'type': message_type.value,
                'payload': order_data,
            },
        )

    def update_order(self, event):
        self.send_json({
            'order': event['payload'],
            'type': event['type'],
        })
