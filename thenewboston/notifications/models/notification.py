from django.db import models

from thenewboston.general.enums import MessageType
from thenewboston.general.models import CreatedModified
from thenewboston.general.utils.database import apply_on_commit


class Notification(CreatedModified):
    owner = models.ForeignKey('users.User', on_delete=models.CASCADE)
    payload = models.JSONField(default=dict)
    is_read = models.BooleanField(default=False)

    def __str__(self):
        return f'Notification ID: {self.pk} | Owner: {self.owner.username}'

    def stream(self):
        from ..consumers import NotificationConsumer
        from ..serializers.notification import NotificationReadSerializer

        apply_on_commit(
            lambda data=NotificationReadSerializer(self).data: NotificationConsumer.
            stream_notification(message_type=MessageType.CREATE_NOTIFICATION, notification_data=data)
        )

    def save(self, *args, should_stream=False, **kwargs):
        if self.is_adding() and should_stream:
            # TODO(dmu) HIGH: Rely on this code everywhere, remove `should_stream` argument and related code
            #                 duplication. Also .create() can be use instead of .save() once we do this refactoring
            self.stream()

        return super().save(*args, **kwargs)  # return for forward compatibility
