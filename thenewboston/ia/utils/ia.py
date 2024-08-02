from django.conf import settings
from django.contrib.auth import get_user_model

from thenewboston.general.clients.openai import MessageRole, OpenAIClient, ResultFormat


def get_ia():
    return get_user_model().objects.get(username='ia')


def ask_ia(question, user=None):
    """
    Generates a chat response to the given question using an AI client.
    """
    # TODO: Do we want to maintain the conversation here?
    chat_completion_text = OpenAIClient.get_instance().get_chat_completion(
        settings.DISCORD_CREATE_RESPONSE_TEMPLATE_NAME,
        extra_messages=get_messages(question, MessageRole.USER.value),
        result_format=ResultFormat.TEXT,
        track=True if user else False,
        tracked_user=user,
    )

    return chat_completion_text


def get_messages(current_message, role, messages=None):
    """
    Appends the current message to the list of messages.
    """
    if messages is None:
        messages = []
    messages.append({'role': role, 'content': current_message})
    return messages
