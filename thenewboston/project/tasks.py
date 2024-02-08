import promptlayer
from django.conf import settings

from thenewboston.general.enums import MessageType
from thenewboston.ia.consumers.message import MessageConsumer
from thenewboston.ia.models import Message
from thenewboston.ia.models.message import SenderType
from thenewboston.ia.serializers.message import MessageReadSerializer
from thenewboston.ia.utils.ia import get_ia

from .celery import app

promptlayer.api_key = settings.PROMPTLAYER_API_KEY
OpenAI = promptlayer.openai.OpenAI


@app.task
def generate_ias_response(conversation_id):
    client = OpenAI()
    prompt = promptlayer.prompts.get('create-message', label='prod')
    system_message_content = prompt['messages'][0]['prompt']['template']
    messages = [{'role': 'system', 'content': system_message_content}]
    messages += get_non_system_messages(conversation_id)

    response = client.chat.completions.create(model='gpt-3.5-turbo', messages=messages)

    message = Message.objects.create(
        conversation_id=conversation_id,
        sender=get_ia(),
        sender_type=SenderType.IA,
        text=response.choices[0].message.content,
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
