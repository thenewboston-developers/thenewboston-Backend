from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from thenewboston.general.consumers.frontend_deployment import FrontendDeploymentConsumer
from thenewboston.general.enums import MessageType
from thenewboston.general.models import FrontendDeployment
from thenewboston.general.serializers.frontend_deployment import FrontendDeploymentSerializer


class Command(BaseCommand):
    help = 'Create and broadcast a frontend deployment after its assets have finished deploying.'

    def add_arguments(self, parser):
        parser.add_argument('--expected-previous-id', required=True, type=int)

    def handle(self, *args, **options):
        with transaction.atomic():
            previous = FrontendDeployment.objects.select_for_update().first()
            previous_id = previous.pk if previous else 0
            if previous_id != options['expected_previous_id']:
                raise CommandError('The latest frontend deployment changed; inspect it before announcing again.')
            # This is an automated deployment, not an action attributed to a member's account.
            deployment = FrontendDeployment.objects.create()
            payload = FrontendDeploymentSerializer(deployment).data
            transaction.on_commit(
                lambda: FrontendDeploymentConsumer.stream_frontend_deployment(
                    message_type=MessageType.UPDATE_FRONTEND_DEPLOYMENT, deployment_data=payload
                )
            )
        self.stdout.write(self.style.SUCCESS(f'Frontend deployment {deployment.pk} announced.'))
