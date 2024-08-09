import json

from django.conf import settings

from thenewboston.general.clients.llm import LLMClient
from thenewboston.general.commands import CustomCommand
from thenewboston.general.utils.json import ResponseEncoder


class Command(CustomCommand):
    help = 'Interact with OpenAI API for testing and debugging'  # noqa: A003

    def add_arguments(self, parser):
        subparsers = self.get_subparsers(parser)
        parser.add_argument('--json', '-j', action='store_true')
        subparsers.required = True

        complete_chat_response_parser = subparsers.add_parser('chat-completion-response')
        complete_chat_response_parser.add_argument('template')
        complete_chat_response_parser.add_argument(
            '--variables', '-v', help='Input variables in JSON format', default='{}'
        )
        complete_chat_response_parser.add_argument('--label', '-l', default=settings.PROMPT_DEFAULT_LABEL)
        complete_chat_response_parser.add_argument('--format-result', '-f', action='store_true')
        complete_chat_response_parser.add_argument('--track', '-t', action='store_true')
        complete_chat_response_parser.add_argument('--tag')

        generate_image_parser = subparsers.add_parser('generate-image')
        generate_image_parser.add_argument('prompt')
        generate_image_parser.add_argument('--size', '-s', default='256x256')

    @staticmethod
    def client():
        return LLMClient.get_instance()

    def print_response(self, response, options):
        if options['json']:
            response = json.dumps(response, cls=ResponseEncoder)

        self.stdout.write(f'Response:\n{response}')

    def handle_chat_completion_response(self, *args, **options):
        variables = json.loads(options['variables'])
        tag = options['tag']
        response = self.client().get_chat_completion(
            options['template'],
            input_variables=variables,
            prompt_label=options['label'],
            format_result=options['format_result'],
            tags=[tag] if tag else None
        )
        self.print_response(response, options)

    def handle_generate_image(self, *args, **options):
        response = self.client().generate_image(options['prompt'], size=options['size']).dict()
        self.print_response(response, options)
