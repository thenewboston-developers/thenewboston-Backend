from celery import shared_task
from django.conf import settings

from thenewboston.general.clients.llm import LLMClient, make_prompt_kwargs
from thenewboston.general.enums import MessageType
from thenewboston.ia.consumers.message import MessageConsumer
from thenewboston.ia.models import Message
from thenewboston.ia.models.conversation import Conversation
from thenewboston.ia.models.message import SenderType
from thenewboston.ia.serializers.message import MessageReadSerializer
from thenewboston.ia.utils.ia import get_ia


@shared_task
def generate_ias_response(conversation_id):
    conversation = Conversation.objects.get(id=conversation_id)

    chat_completion_text = LLMClient.get_instance().get_chat_completion(
        input_variables={'messages': get_non_system_messages(conversation_id)},
        tracked_user=conversation.owner,
        **make_prompt_kwargs(settings.CREATE_MESSAGE_PROMPT_NAME),
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
            results.append({'role': 'assistant', 'content': [{'type': 'text', 'text': message.text}]})
        elif message.sender_type == SenderType.USER:
            results.append({'role': 'user', 'content': [{'type': 'text', 'text': message.text}]})

    return results
