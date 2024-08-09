import json

from anthropic import BaseModel as AnthropicBaseModel
from openai import BaseModel as OpenAIBaseModel


class ResponseEncoder(json.JSONEncoder):

    def default(self, obj):
        if isinstance(obj, (OpenAIBaseModel, AnthropicBaseModel)):
            return obj.to_dict()

        return super().default(obj)
