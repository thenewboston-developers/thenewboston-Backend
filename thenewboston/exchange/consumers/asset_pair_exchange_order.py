from asgiref.sync import async_to_sync
from channels.generic.websocket import JsonWebsocketConsumer
from channels.layers import get_channel_layer


class AssetPairExchangeOrderConsumer(JsonWebsocketConsumer):

    def connect(self):
        """Accept the incoming connection and add the client to the asset pair group."""
        self.primary_currency = self.scope['url_route']['kwargs']['primary_currency']
        self.secondary_currency = self.scope['url_route']['kwargs']['secondary_currency']
        self.group_name = f'exchange_orders_{self.primary_currency}_{self.secondary_currency}'

        self.accept()
        async_to_sync(get_channel_layer().group_add)(self.group_name, self.channel_name)

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
        """Remove the client from the asset pair group on disconnection."""
        async_to_sync(get_channel_layer().group_discard)(self.group_name, self.channel_name)

    @classmethod
    def stream_exchange_order(cls, *, message_type, order_data, primary_currency_id, secondary_currency_id):
        """
        Send order details to the asset pair group.
        message_type indicates the type of the order action and order_data contains the order details.
        """
        channel_layer = get_channel_layer()
        group_name = f'exchange_orders_{primary_currency_id}_{secondary_currency_id}'
        order_event = {
            'payload': order_data,
            'type': message_type.value,
        }
        async_to_sync(channel_layer.group_send)(group_name, order_event)

    def update_exchange_order(self, event):
        """
        Send order update details to the client. The event is expected to contain the 'payload' with order details
        and 'type' indicating the action.
        """
        self.send_json({
            'exchange_order': event['payload'],
            'type': event['type'],
        })
