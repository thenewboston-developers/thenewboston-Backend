import logging

from asgiref.sync import async_to_sync
from channels.generic.websocket import JsonWebsocketConsumer
from channels.layers import get_channel_layer
from django.conf import settings

logger = logging.getLogger(__name__)


class AuthenticatedUserConsumer(JsonWebsocketConsumer):
    """
    Base for the sockets that stream the private events of one user. The path names the user, and only a connection
    authenticated as that same user may join the user's group.
    """

    group_name = None

    def connect(self):
        user_id = self.scope['url_route']['kwargs']['user_id']

        if not self.is_allowed(user_id):
            self.close()
            return

        self.user_id = user_id
        self.group_name = self.get_group_name(user_id)
        self.accept()
        async_to_sync(get_channel_layer().group_add)(self.group_name, self.channel_name)

    def disconnect(self, close_code):
        """Remove the client from the group on disconnection."""
        if self.group_name:
            async_to_sync(get_channel_layer().group_discard)(self.group_name, self.channel_name)

    @staticmethod
    def get_group_name(user_id):
        raise NotImplementedError

    def is_allowed(self, user_id):
        user = self.scope['user']

        if not user.is_authenticated:
            reason = self.scope['authentication_error']
        elif str(user.pk) != user_id:
            reason = f'access token belongs to user {user.pk}'
        else:
            return True

        # %r, because the path is the client's to choose and may contain line breaks
        if settings.ENFORCE_WEBSOCKET_AUTHENTICATION:
            logger.info('Rejected websocket connection to %r: %s', self.scope['path'], reason)
            return False

        logger.info(
            'Accepted unauthenticated websocket connection to %r: %s (ENFORCE_WEBSOCKET_AUTHENTICATION is off)',
            self.scope['path'],
            reason,
        )
        return True
