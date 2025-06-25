from asgiref.sync import async_to_sync
from channels.generic.websocket import JsonWebsocketConsumer
from channels.layers import get_channel_layer


class FrontendDeploymentConsumer(JsonWebsocketConsumer):

    GROUP_NAME = 'deployment_updates'

    def connect(self):
        self.accept()
        async_to_sync(get_channel_layer().group_add)(self.GROUP_NAME, self.channel_name)

    def disconnect(self, close_code):
        async_to_sync(get_channel_layer().group_discard)(self.GROUP_NAME, self.channel_name)

    def deployment_update(self, event):
        self.send_json({
            'type': 'deployment_update',
            'deployed_at': event['deployed_at'],
        })

    @classmethod
    def broadcast_deployment_update(cls, deployed_at):
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send
                      )(cls.GROUP_NAME, {
                          'type': 'deployment_update',
                          'deployed_at': deployed_at.isoformat(),
                      })
