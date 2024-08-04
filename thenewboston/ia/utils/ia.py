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

    metadata = {}

    if user:
        metadata = {'user_id': str(user.id), 'username': user.username}

    response = promptlayer_client.run(
        prompt_name=settings.DISCORD_CREATE_RESPONSE_TEMPLATE_NAME,
        input_variables={'question': question},
        prompt_release_label=settings.PROMPT_TEMPLATE_LABEL,
        metadata=metadata,
        tags=['discord_bot_response']
    )
    chat_completion_text = response['raw_response'].choices[0].message.content
    return chat_completion_text
