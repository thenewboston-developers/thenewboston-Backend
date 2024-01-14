from django.conf import settings
from openai import OpenAI

from thenewboston.ia.models import Message
from thenewboston.ia.models.message import SenderType
from thenewboston.ia.utils.ia import get_ia

from .celery import app


@app.task
def generate_ias_response(conversation_id):
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    messages = get_messages(conversation_id)
    response = client.chat.completions.create(
        model='gpt-3.5-turbo',
        messages=messages,
    )
    response_dict = response.dict()
    text = response_dict['choices'][0]['message']['content']

    Message.objects.create(conversation_id=conversation_id, sender=get_ia(), sender_type=SenderType.IA, text=text)


def get_messages(conversation_id):
    messages = Message.objects.filter(conversation__id=conversation_id).order_by('created_date')
    results = [
        {
            'role': 'system',
            'content': 'Your name is Ia. Your job is to ask the user questions to get to know them.'
        },
    ]

    for message in messages:
        if message.sender_type == SenderType.IA:
            results.append({'role': 'assistant', 'content': message.text})
        elif message.sender_type == SenderType.USER:
            results.append({'role': 'user', 'content': message.text})

    return results
