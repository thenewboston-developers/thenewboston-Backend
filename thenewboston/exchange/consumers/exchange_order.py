from asgiref.sync import async_to_sync
from channels.generic.websocket import JsonWebsocketConsumer
from channels.layers import get_channel_layer

from ..models import AssetPair


class ExchangeOrderConsumer(JsonWebsocketConsumer):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.subscribed_asset_pairs = set()

    def connect(self):
        """Accept the incoming connection."""
        self.accept()

    def create_exchange_order(self, event):
        """
        Send order creation details to the client. The event is expected to contain the 'payload' with order details.
        """
        self.send_json({
            'exchange_order': event['payload'],
            'type': event['type'],
        })

    def disconnect(self, close_code):
        """Remove the client from all subscribed asset pair groups on disconnection."""
        for asset_pair_id in self.subscribed_asset_pairs:
            group_name = self.get_group_name(asset_pair_id)
            async_to_sync(get_channel_layer().group_discard)(group_name, self.channel_name)

    @staticmethod
    def get_group_name(asset_pair_id):
        """Construct a unique group name for a given asset pair."""
        return f'exchange_orders_{asset_pair_id}'

    def receive_json(self, content, **kwargs):
        """Handle incoming WebSocket messages for subscribe/unsubscribe actions."""
        action = content.get('action')
        asset_pair_id = content.get('asset_pair_id')

        if not action or not asset_pair_id:
            self.send_json({'error': 'Invalid message format. Required fields: action, asset_pair_id'})
            return

        # Ensure asset_pair_id is an integer for consistency
        try:
            asset_pair_id = int(asset_pair_id)
        except (ValueError, TypeError):
            self.send_json({'error': 'asset_pair_id must be a valid integer'})
            return

        if action == 'subscribe':
            self.subscribe_to_asset_pair(asset_pair_id)
        elif action == 'unsubscribe':
            self.unsubscribe_from_asset_pair(asset_pair_id)
        else:
            self.send_json({'error': f'Unknown action: {action}'})

    @classmethod
    def get_or_create_asset_pair(cls, primary_currency_id, secondary_currency_id):
        """Get or create an AssetPair for the given currency IDs."""
        asset_pair, created = AssetPair.objects.get_or_create(
            primary_currency_id=primary_currency_id, secondary_currency_id=secondary_currency_id
        )
        return asset_pair

    @classmethod
    def stream_exchange_order(cls, *, message_type, order_data, primary_currency_id, secondary_currency_id):
        """
        Send order details to the group associated with the asset pair.
        message_type indicates the type of the order action, order_data contains the order details.
        """
        # Get or create the asset pair to find its ID
        asset_pair = cls.get_or_create_asset_pair(primary_currency_id, secondary_currency_id)
        asset_pair_id = asset_pair.id

        channel_layer = get_channel_layer()
        order_event = {
            'payload': order_data,
            'type': message_type.value,
        }
        async_to_sync(channel_layer.group_send)(cls.get_group_name(asset_pair_id), order_event)

    def subscribe_to_asset_pair(self, asset_pair_id):
        """Add the client to the asset pair group."""
        if asset_pair_id not in self.subscribed_asset_pairs:
            group_name = self.get_group_name(asset_pair_id)
            async_to_sync(get_channel_layer().group_add)(group_name, self.channel_name)
            self.subscribed_asset_pairs.add(asset_pair_id)
            self.send_json({'success': f'Subscribed to asset pair: {asset_pair_id}'})

    def unsubscribe_from_asset_pair(self, asset_pair_id):
        """Remove the client from the asset pair group."""
        if asset_pair_id in self.subscribed_asset_pairs:
            group_name = self.get_group_name(asset_pair_id)
            async_to_sync(get_channel_layer().group_discard)(group_name, self.channel_name)
            self.subscribed_asset_pairs.remove(asset_pair_id)
            self.send_json({'success': f'Unsubscribed from asset pair: {asset_pair_id}'})

    def update_exchange_order(self, event):
        """
        Send order update details to the client. The event is expected to contain the 'payload' with order details.
        """
        self.send_json({
            'exchange_order': event['payload'],
            'type': event['type'],
        })
