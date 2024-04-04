import json

from django.conf import settings

from thenewboston.general.clients.openai import OpenAIClient, ResultFormat
from thenewboston.general.commands import CustomCommand


class Command(CustomCommand):
    help = 'Interact with OpenAI API for testing and debugging'  # noqa: A003

    def add_arguments(self, parser):
        subparsers = self.get_subparsers(parser)

        complete_chat_response_parser = subparsers.add_parser('chat-completion-response')
        complete_chat_response_parser.add_argument('template')
        complete_chat_response_parser.add_argument(
            '--variables', '-v', help='Input variables in JSON format', default='{}'
        )
        complete_chat_response_parser.add_argument('--label', '-l', default=settings.PROMPT_TEMPLATE_LABEL)
        complete_chat_response_parser.add_argument(
            '--result-format',
            '-r',
            choices=[item.value for item in ResultFormat],
            default=ResultFormat.RAW.value,
        )
        complete_chat_response_parser.add_argument('--track', '-t', action='store_true')

        generate_image_parser = subparsers.add_parser('generate-image')
        generate_image_parser.add_argument('prompt')
        generate_image_parser.add_argument('--size', '-s', default='256x256')

    @staticmethod
    def client():
        return OpenAIClient.get_instance()

    def handle_chat_completion_response(self, *args, **options):
        variables = json.loads(options['variables'])
        response = self.client().get_chat_completion(
            options['template'],
            input_variables=variables,
            label=options['label'],
            result_format=ResultFormat(options['result_format'])
        )

        self.stdout.write(f'Response:\n{response}')

    def handle_generate_image(self, *args, **options):
        response = self.client().generate_image(options['prompt'], size=options['size']).dict()
        self.stdout.write(f'Response:\n{response}')
