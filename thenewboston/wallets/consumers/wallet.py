from asgiref.sync import async_to_sync
from channels.generic.websocket import JsonWebsocketConsumer
from channels.layers import get_channel_layer


class WalletConsumer(JsonWebsocketConsumer):
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
        return f'user_{user_id}_wallet'

    @classmethod
    def stream_wallet(cls, *, message_type, wallet_data):
        """
        Send wallet details to the group associated with the wallet owner.
        message_type indicates the type of the action and wallet_data contains the wallet details.
        """
        channel_layer = get_channel_layer()
        wallet_owner_id = wallet_data['owner']
        wallet_event = {
            'payload': wallet_data,
            'type': message_type.value,
        }
        async_to_sync(channel_layer.group_send)(cls.get_group_name(wallet_owner_id), wallet_event)

    def update_wallet(self, event):
        """
        Send wallet update details to the client. The event is expected to contain the 'payload' with wallet details
        and 'type' indicating the action.
        """
        self.send_json({'type': event['type'], 'wallet': event['payload']})
