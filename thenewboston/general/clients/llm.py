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


def make_prompt_kwargs(prompt_name: str) -> dict:
    parts = prompt_name.split(':')
    return {'prompt_name': parts[0], 'prompt_label': settings.PROMPT_DEFAULT_LABEL if len(parts) < 2 else parts[1]}


class LLMClient:
    """
    This class encapsulates Promptlayer and LLM integration logic
    """
    _instance = None

    def __init__(self, promptlayer_api_key, openai_api_key=None, anthropic_api_key=None):
        self.promptlayer_api_key = promptlayer_api_key
        if not openai_api_key and not anthropic_api_key:
            raise ValueError('At least one of LLM API keys must be provided: openai_api_key or anthropic_api_key')

        self.openai_api_key = openai_api_key
        self.anthropic_api_key = anthropic_api_key

    @classmethod
    def get_instance(cls):
        if (instance := cls._instance) is None:
            cls._instance = instance = cls(
                promptlayer_api_key=settings.PROMPTLAYER_API_KEY,
                openai_api_key=settings.OPENAI_API_KEY,
                anthropic_api_key=settings.ANTHROPIC_API_KEY,
            )

        return instance

    @property
    def promptlayer_client(self):
        # TODO(dmu) MEDIUM: Consider using async OpenAI client
        # Since we are using PromptLayer.run() method there is no explicit way to provide OpenAI API key, so
        # we have to update environment variable to make it read from there
        if openai_api_key := self.openai_api_key:
            os.environ['OPENAI_API_KEY'] = openai_api_key
        if anthropic_api_key := self.anthropic_api_key:
            os.environ['ANTHROPIC_API_KEY'] = anthropic_api_key

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
        prompt_label=settings.PROMPT_DEFAULT_LABEL,
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
            prompt_release_label=prompt_label,
            input_variables=input_variables,
            **kwargs,
        )

        if format_result:
            raw_response = promptlayer_result['raw_response']
            model = promptlayer_result['prompt_blueprint']['metadata']['model']
            provider = model['provider']
            match provider:
                case 'openai':
                    result = raw_response.choices[0].message.content
                    if model.get('parameters', {}).get('response_format',
                                                       {}).get('type') == 'json_object':  # noqa: E129
                        try:
                            result = json.loads(result)
                        except Exception:
                            result = None
                case 'anthropic':
                    # TODO(dmu) MEDIUM: anthropic does have message type, but it is 'text' even for actual JSON
                    #                   Figure out how to make it return the correct type and improve this part
                    result = raw_response.content[0].text
                    try:
                        result = json.loads(result)
                    except Exception:
                        pass  # It was not JSON, see the TODO above for more reliable formatting
                case _:
                    logger.warning('Unsupported LLM provider: %s', provider)
                    result = promptlayer_result
        else:
            result = promptlayer_result

        return result

    def generate_image(self, prompt: str, quantity: int = 1, model=None, size=None, quality=None):
        model = model or settings.OPENAI_IMAGE_GENERATION_MODEL
        size = size or settings.OPENAI_IMAGE_GENERATION_DEFAULT_SIZE
        quality = quality or settings.OPENAI_IMAGE_GENERATION_DEFAULT_QUALITY
        return self.openai_client.images.generate(model=model, prompt=prompt, n=quantity, quality=quality, size=size)
