from asgiref.sync import async_to_sync
from channels.generic.websocket import JsonWebsocketConsumer
from channels.layers import get_channel_layer


class ExchangeOrderConsumer(JsonWebsocketConsumer):
    GROUP_NAME = 'exchange_orders'

    def connect(self):
        """Accept the incoming connection and add the client to the exchange_orders group."""
        self.accept()
        async_to_sync(get_channel_layer().group_add)(self.GROUP_NAME, self.channel_name)

    def create_exchange_order(self, event):
        """
        Send order creation details to the client. The event is expected to contain the 'payload' with order details
        and 'type' indicating the action.
        """
        self.send_json({
            'exchange_order': event['payload'],
            'type': event['type'],
        })

    def disconnect(self, close_code):
        """Remove the client from the exchange_orders group on disconnection."""
        async_to_sync(get_channel_layer().group_discard)(self.GROUP_NAME, self.channel_name)

    @classmethod
    def stream_exchange_order(cls, *, message_type, order_data):
        """
        Send order details to the exchange_orders group.
        message_type indicates the type of the order action and order_data contains the order details.
        """
        channel_layer = get_channel_layer()
        order_event = {
            'payload': order_data,
            'type': message_type.value,
        }
        async_to_sync(channel_layer.group_send)(cls.GROUP_NAME, order_event)

    def update_exchange_order(self, event):
        """
        Send order update details to the client. The event is expected to contain the 'payload' with order details
        and 'type' indicating the action.
        """
        self.send_json({
            'exchange_order': event['payload'],
            'type': event['type'],
        })
