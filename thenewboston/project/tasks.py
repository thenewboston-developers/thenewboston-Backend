from celery import shared_task
from django.conf import settings

from thenewboston.general.clients.openai import OpenAIClient, ResultFormat
from thenewboston.general.enums import MessageType
from thenewboston.ia.consumers.message import MessageConsumer
from thenewboston.ia.models import Message
from thenewboston.ia.models.message import SenderType
from thenewboston.ia.serializers.message import MessageReadSerializer
from thenewboston.ia.utils.ia import get_ia
from thenewboston.users.models import User


# TODO(dmu) MEDIUM: Move this code somewhere from here. It should live in some Django app
@shared_task
def generate_ias_response(conversation_id, tracked_user_id=None):
    if tracked_user_id:
        tracked_user = User.objects.get(id=tracked_user_id)
    else:
        tracked_user = None

    chat_completion_text = OpenAIClient.get_instance().get_chat_completion(
        settings.CREATE_MESSAGE_TEMPLATE_NAME,
        track=True if tracked_user else False,
        extra_messages=get_non_system_messages(conversation_id),
        result_format=ResultFormat.TEXT,
        tracked_user=tracked_user,
    )

    message = Message.objects.create(
        conversation_id=conversation_id,
        sender=get_ia(),
        sender_type=SenderType.IA,
        text=chat_completion_text,
    )
    message_data = MessageReadSerializer(message).data
    MessageConsumer.stream_message(message_type=MessageType.CREATE_MESSAGE, message_data=message_data)


def get_non_system_messages(conversation_id):
    messages = Message.objects.filter(conversation__id=conversation_id).order_by('created_date')
    results = []

    for message in messages:
        if message.sender_type == SenderType.IA:
            results.append({'role': 'assistant', 'content': message.text})
        elif message.sender_type == SenderType.USER:
            results.append({'role': 'user', 'content': message.text})

    return results
