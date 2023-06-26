from channels.generic.websocket import JsonWebsocketConsumer


class OrderJsonWebsocketConsumer(JsonWebsocketConsumer):

    def connect(self):
        self.accept()

    def disconnect(self, close_code):
        pass

    def receive_json(self, content, **kwargs):
        # Echo the same message back to the client
        self.send_json(content)
