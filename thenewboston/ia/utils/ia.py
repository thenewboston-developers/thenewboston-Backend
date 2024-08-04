from django.conf import settings
from django.contrib.auth import get_user_model
from promptlayer import PromptLayer

promptlayer_client = PromptLayer(api_key=settings.PROMPTLAYER_API_KEY)


def get_ia():
    return get_user_model().objects.get(username='ia')


def ask_ia(question, user=None):
    """
    Generates a chat response to the given question using PromptLayer.
    """
    input_variables = {'question': question}

    metadata = {}
    if user:
        metadata = {'user_id': str(user.id), 'username': user.username}

    response = promptlayer_client.run(
        prompt_name=settings.DISCORD_CREATE_RESPONSE_TEMPLATE_NAME,
        input_variables=input_variables,
        prompt_release_label=settings.PROMPT_TEMPLATE_LABEL,
        metadata=metadata,
        tags=['discord_bot_response']
    )

    # Extract the chat completion text from the response
    chat_completion_text = response['raw_response'].choices[0].message.content

    return chat_completion_text


def get_messages(current_message, role, messages=None):
    """
    Appends the current message to the list of messages.
    """
    if messages is None:
        messages = []
    messages.append({'role': role, 'content': current_message})
    return messages
