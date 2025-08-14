from asgiref.sync import async_to_sync
from channels.generic.websocket import JsonWebsocketConsumer
from channels.layers import get_channel_layer


class TradeConsumer(JsonWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.subscribed_tickers = set()

    def connect(self):
        """Accept the incoming connection."""
        self.accept()

    def create_trade(self, event):
        """
        Send trade creation details to the client. The event is expected to contain the 'payload' with trade details
        and 'type' indicating the action.
        """
        self.send_json({'trade': event['payload'], 'type': event['type']})

    def disconnect(self, close_code):
        """Remove the client from all subscribed ticker groups on disconnection."""
        for ticker in self.subscribed_tickers:
            group_name = self.get_group_name(ticker)
            async_to_sync(get_channel_layer().group_discard)(group_name, self.channel_name)

    @staticmethod
    def get_group_name(ticker):
        """Construct a unique group name for a given ticker."""
        return f'trades_{ticker}'

    def receive_json(self, content, **kwargs):
        """Handle incoming WebSocket messages for subscribe/unsubscribe actions."""
        action = content.get('action')
        ticker = content.get('ticker')

        if not action or not ticker:
            self.send_json({'error': 'Invalid message format. Required fields: action, ticker'})
            return

        if action == 'subscribe':
            self.subscribe_to_ticker(ticker)
        elif action == 'unsubscribe':
            self.unsubscribe_from_ticker(ticker)
        else:
            self.send_json({'error': f'Unknown action: {action}'})

    @classmethod
    def stream_trade(cls, *, message_type, trade_data, ticker):
        """
        Send trade details to the group associated with the trade's primary currency ticker.
        message_type indicates the type of the action, trade_data contains the trade details,
        and ticker specifies which currency group to broadcast to.
        """
        channel_layer = get_channel_layer()
        trade_event = {'payload': trade_data, 'type': message_type.value}
        async_to_sync(channel_layer.group_send)(cls.get_group_name(ticker), trade_event)

    def subscribe_to_ticker(self, ticker):
        """Add the client to the ticker group."""
        if ticker not in self.subscribed_tickers:
            group_name = self.get_group_name(ticker)
            async_to_sync(get_channel_layer().group_add)(group_name, self.channel_name)
            self.subscribed_tickers.add(ticker)
            self.send_json({'success': f'Subscribed to ticker: {ticker}'})

    def unsubscribe_from_ticker(self, ticker):
        """Remove the client from the ticker group."""
        if ticker in self.subscribed_tickers:
            group_name = self.get_group_name(ticker)
            async_to_sync(get_channel_layer().group_discard)(group_name, self.channel_name)
            self.subscribed_tickers.remove(ticker)
            self.send_json({'success': f'Unsubscribed from ticker: {ticker}'})
