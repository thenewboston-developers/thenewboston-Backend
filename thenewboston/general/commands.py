from django.core.management.base import BaseCommand, CommandError


class CustomCommand(BaseCommand):
    @staticmethod
    def get_subparsers(parser):
        return parser.add_subparsers(help='subcommand', dest='subcommand', required=True)

    def handle(self, *args, **options):
        subcommand = options['subcommand']
        try:
            command_handler = getattr(self, f'handle_{subcommand.replace("-", "_")}')
        except AttributeError:
            raise CommandError(f'Invalid subcommand: {subcommand}')

        command_handler(*args, **options)
        self.stdout.write(self.style.SUCCESS(f'{subcommand} done'))
