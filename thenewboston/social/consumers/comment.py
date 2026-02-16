from asgiref.sync import async_to_sync
from channels.generic.websocket import JsonWebsocketConsumer
from channels.layers import get_channel_layer


class CommentConsumer(JsonWebsocketConsumer):
    def connect(self):
        self.post_id = self.scope['url_route']['kwargs']['post_id']
        self.group_name = self.get_group_name(self.post_id)
        self.accept()
        async_to_sync(get_channel_layer().group_add)(self.group_name, self.channel_name)

    def disconnect(self, close_code):
        async_to_sync(get_channel_layer().group_discard)(self.group_name, self.channel_name)

    @staticmethod
    def get_group_name(post_id):
        return f'post_{post_id}_comments'

    @classmethod
    def stream_comment(cls, *, message_type, comment_data, post_id):
        channel_layer = get_channel_layer()
        event = {'payload': comment_data, 'type': message_type.value}
        async_to_sync(channel_layer.group_send)(cls.get_group_name(post_id), event)

    @classmethod
    def stream_comment_delete(cls, *, message_type, comment_id, post_id):
        channel_layer = get_channel_layer()
        event = {'payload': comment_id, 'type': message_type.value}
        async_to_sync(channel_layer.group_send)(cls.get_group_name(post_id), event)

    def create_comment(self, event):
        self.send_json({'comment': event['payload'], 'type': event['type']})

    def delete_comment(self, event):
        self.send_json({'comment_id': event['payload'], 'type': event['type']})

    def update_comment(self, event):
        self.send_json({'comment': event['payload'], 'type': event['type']})
