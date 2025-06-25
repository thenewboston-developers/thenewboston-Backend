from asgiref.sync import async_to_sync
from channels.generic.websocket import JsonWebsocketConsumer
from channels.layers import get_channel_layer


class FrontendDeploymentConsumer(JsonWebsocketConsumer):
    GROUP_NAME = 'frontend_deployments'

    def connect(self):
        self.accept()
        async_to_sync(get_channel_layer().group_add)(self.GROUP_NAME, self.channel_name)

    def disconnect(self, close_code):
        async_to_sync(get_channel_layer().group_discard)(self.GROUP_NAME, self.channel_name)

    @classmethod
    def stream_frontend_deployment(cls, *, message_type, deployment_data):
        channel_layer = get_channel_layer()
        deployment_event = {
            'payload': deployment_data,
            'type': message_type.value,
        }
        async_to_sync(channel_layer.group_send)(cls.GROUP_NAME, deployment_event)

    def update_frontend_deployment(self, event):
        self.send_json({
            'frontend_deployment': event['payload'],
            'type': event['type'],
        })
