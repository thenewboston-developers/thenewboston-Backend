import json

from thenewboston.general.clients.llm import LLMClient
from thenewboston.general.tests.vcr import assert_played, yield_cassette
from thenewboston.general.utils.json import ResponseEncoder


def test_get_chat_completion__anthropic():
    with (
        yield_cassette('llm_client__get_chat_completion__anthropic.yaml') as cassette,
        assert_played(cassette, count=3),
    ):
        response = LLMClient.get_instance().get_chat_completion(
            'testing-dmu',
            input_variables={'message': 'what is your name? return JSON'},
            prompt_label='dev',
        )

    assert response == {'name': 'Claude'}

    with (
        yield_cassette('llm_client__get_chat_completion__anthropic.yaml') as cassette,
        assert_played(cassette, count=3),
    ):
        response = LLMClient.get_instance().get_chat_completion(
            'testing-dmu',
            input_variables={'message': 'what is your name? return JSON'},
            prompt_label='dev',
            format_result=False,
        )

    assert json.loads(json.dumps(response, cls=ResponseEncoder)) == {
        'request_id': 72305093,
        'raw_response': {
            'id': 'msg_01AzbQ7d6oSQs9ny858MaaKV',
            'content': [{
                'text': '{"name":"Claude"}',
                'type': 'text'
            }],
            'model': 'claude-3-5-sonnet-20240620',
            'role': 'assistant',
            'stop_reason': 'end_turn',
            'stop_sequence': None,
            'type': 'message',
            'usage': {
                'input_tokens': 26,
                'output_tokens': 8
            }
        },
        'prompt_blueprint': {
            'commit_message': None,
            'metadata': {
                'model': {
                    'name': 'claude-3-5-sonnet-20240620',
                    'parameters': {
                        'max_tokens': 256,
                        'stream': False,
                        'system': 'Give the shortest reply possible: 3 words at most',
                        'temperature': 1,
                        'top_k': 0,
                        'top_p': 0
                    },
                    'provider': 'anthropic'
                }
            },
            'prompt_template': {
                'function_call': None,
                'functions': None,
                'input_variables': ['"name"'],
                'messages': [{
                    'content': [{
                        'text': 'Give the shortest reply possible: 3 words at most',
                        'type': 'text'
                    }],
                    'input_variables': [],
                    'name': None,
                    'raw_request_display_role': '',
                    'role': 'system',
                    'template_format': 'f-string'
                }, {
                    'content': [{
                        'text': 'what is your name? return JSON',
                        'type': 'text'
                    }],
                    'input_variables': [],
                    'name': None,
                    'raw_request_display_role': 'user',
                    'role': 'user',
                    'template_format': 'f-string'
                }, {
                    'content': [{
                        'text': '{"name":"Claude"}',
                        'type': 'text'
                    }],
                    'function_call': None,
                    'input_variables': ['"name"'],
                    'name': None,
                    'raw_request_display_role': 'assistant',
                    'role': 'assistant',
                    'template_format': 'f-string',
                    'tool_calls': None
                }],
                'tool_choice': None,
                'tools': [],
                'type': 'chat'
            },
            'provider_base_url_name': None,
            'report_id': None
        }
    }
