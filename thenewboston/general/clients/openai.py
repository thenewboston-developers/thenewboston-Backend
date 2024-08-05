import json
import logging
import os
from typing import TYPE_CHECKING, Optional  # noqa: I101

from django.conf import settings
from openai import OpenAI
from promptlayer import PromptLayer

if TYPE_CHECKING:
    from thenewboston.users.models import User

logger = logging.getLogger(__name__)


class OpenAIClient:
    # TODO(dmu) MEDIUM: Maybe we should rename it to LLMClient once we start supporting other AI providers
    """
    This class encapsulates Promptlayer and OpenAI integration logic, so the code that uses it is cleaner
    """
    _instance = None

    def __init__(self, openai_api_key, promptlayer_api_key):
        self.openai_api_key = openai_api_key
        self.promptlayer_api_key = promptlayer_api_key

    @classmethod
    def get_instance(cls):
        if (instance := cls._instance) is None:
            cls._instance = instance = cls(
                openai_api_key=settings.OPENAI_API_KEY,
                promptlayer_api_key=settings.PROMPTLAYER_API_KEY,
            )

        return instance

    @property
    def promptlayer_client(self):
        # TODO(dmu) MEDIUM: Consider using async OpenAI client
        # Since we are using PromptLayer.run() method there is no explicit way to provide OpenAI API key, so
        # we have to update environment variable to make it read from there
        os.environ['OPENAI_API_KEY'] = self.openai_api_key
        return PromptLayer(api_key=self.promptlayer_api_key)

    @property
    def openai_client(self):
        # TODO(dmu) MEDIUM: Consider using async OpenAI client
        return OpenAI(api_key=self.openai_api_key)

    def get_chat_completion(
        self,
        prompt_name,
        *,
        input_variables=None,
        label=settings.PROMPT_TEMPLATE_LABEL,
        tracked_user: Optional['User'] = None,
        tags=None,
        format_result=True,
    ):
        metadata = {'environment': settings.ENV_NAME}
        if tracked_user:
            metadata['user_id'] = str(tracked_user.id)
            metadata['username'] = tracked_user.username

        kwargs = {'metadata': metadata}

        if tags:
            kwargs['tags'] = tags

        promptlayer_result = self.promptlayer_client.run(
            prompt_name=prompt_name,
            prompt_release_label=label,
            input_variables=input_variables,
            **kwargs,
        )
        if format_result:
            result = promptlayer_result['raw_response'].choices[0].message.content
            prompt_blueprint = promptlayer_result['prompt_blueprint']
            if ((model := prompt_blueprint.get('metadata', {}).get('model', {})) and
                model.get('parameters', {}).get('response_format', {}).get('type') == 'json_object'):  # noqa: E129
                try:
                    result = json.loads(result)
                except Exception:
                    result = None
        else:
            result = promptlayer_result

        return result

    def generate_image(self, prompt: str, quantity: int = 1, model=None, size=None, quality=None):
        model = model or settings.OPENAI_IMAGE_GENERATION_MODEL
        size = size or settings.OPENAI_IMAGE_GENERATION_DEFAULT_SIZE
        quality = quality or settings.OPENAI_IMAGE_GENERATION_DEFAULT_QUALITY
        return self.openai_client.images.generate(model=model, prompt=prompt, n=quantity, quality=quality, size=size)
