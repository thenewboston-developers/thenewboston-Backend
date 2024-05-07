import json
import logging
from enum import Enum
from typing import TYPE_CHECKING, Optional  # noqa: I101

import jinja2
import promptlayer
from django.conf import settings

if TYPE_CHECKING:
    from thenewboston.users.models import User

logger = logging.getLogger(__name__)


class ResultFormat(Enum):
    RAW = 'raw'
    TEXT = 'text'
    JSON = 'json'


def make_messages_from_template(template, *, variables=None):
    env = jinja2.Environment()

    messages = []
    for template_message in template['prompt_template']['messages']:
        template_content_text = template_message['content'][0]['text']

        if input_variables_set := set(template_message['input_variables']) and variables:
            context_variables = {key: value for key, value in variables.items() if key in input_variables_set}
            template_format = template_message['template_format']
            match template_format:
                case 'jinja2':
                    content = env.from_string(template_content_text).render(**context_variables)
                case '':
                    content = template_content_text.format(**context_variables)
                case _:
                    # TODO(dmu) MEDIUM: Should we raise an exception instead
                    logger.warning('Unsupported template format: %s', template_format)
                    content = template_content_text
        else:
            content = template_content_text

        messages.append({'role': template_message['role'], 'content': content})

    return messages


def extract_chat_completion_content(response):
    return response.choices[0].message.content


class OpenAIClient:
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

    def client(self):
        # TODO(dmu) LOW: Using global variables is a bad idea. Change `promptlayer.api_key = promptlayer_api_key`
        #                once PromptLayer fix it.
        promptlayer.api_key = self.promptlayer_api_key
        # TODO(dmu) MEDIUM: Consider using async OpenAI client
        return promptlayer.openai.OpenAI(api_key=self.openai_api_key)

    def get_chat_completion(
        self,
        template,
        *,
        extra_messages=(),
        input_variables=None,
        label=settings.PROMPT_TEMPLATE_LABEL,
        result_format: ResultFormat = ResultFormat.RAW,
        track=False,
        tracked_user: Optional['User'] = None,
    ):
        # TODO(dmu) LOW: Once PromptPlayer improve software design and get rid of global object move getting client
        #                closer to the first usage
        client = self.client()
        template = promptlayer.templates.get(template, {'label': label})

        template_model = template['metadata']['model']
        kwargs = template_model['parameters'].copy()
        kwargs['model'] = settings.OPENAI_CHAT_COMPLETION_MODEL_OVERRIDE or template_model['name']
        if result_format == ResultFormat.JSON:
            kwargs['response_format'] = {'type': 'json_object'}

        messages = make_messages_from_template(template, variables=input_variables)
        messages.extend(extra_messages)

        compound_result = client.chat.completions.create(
            messages=messages,
            return_pl_id=track,
            **kwargs,
        )

        if track:
            result, pl_request_id = compound_result
            metadata = {'environment': settings.ENV_NAME}
            if tracked_user:
                metadata['user_id'] = str(tracked_user.id)
                metadata['username'] = tracked_user.username

            promptlayer.track.metadata(request_id=pl_request_id, metadata=metadata)
        else:
            result = compound_result

        match result_format:
            case ResultFormat.TEXT:
                result = extract_chat_completion_content(result)
            case ResultFormat.JSON:
                result = extract_chat_completion_content(result)
                try:
                    result = json.loads(result)
                except Exception:
                    result = None

        return result

    def generate_image(
        self,
        prompt: str,
        quantity: int = 1,
        model=None,
        size=None,
        quality=None,
    ):
        model = model or settings.OPENAI_IMAGE_GENERATION_MODEL
        size = size or settings.OPENAI_IMAGE_GENERATION_DEFAULT_SIZE
        quality = quality or settings.OPENAI_IMAGE_GENERATION_DEFAULT_QUALITY
        return self.client().images.generate(model=model, prompt=prompt, n=quantity, quality=quality, size=size)
