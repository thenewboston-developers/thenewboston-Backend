import logging

from django.core.management.base import BaseCommand

from thenewboston.exchange.order_processing.engine import OrderProcessingEngine
from thenewboston.general.exceptions import ThenewbostonRuntimeError

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Order processing engine'  # noqa: A003

    def add_arguments(self, parser):
        parser.add_argument('--force-run', '-f', action='store_true')

    def handle(self, *args, force_run, **options):
        try:
            OrderProcessingEngine().run(force=force_run)
        except ThenewbostonRuntimeError as ex:
            logger.error('Order processing engine failed: %s', ex)
