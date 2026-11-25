import json

from django.core.management.base import BaseCommand, CommandError

from thenewboston.casino.registry import registry
from thenewboston.casino.services import reconcile_fund


class Command(BaseCommand):
    help = 'Verify casino ledger, reservations, and installed payout rules without moving coins.'

    def handle(self, *args, **options):
        try:
            if not registry.games:
                raise ValueError('No casino games are installed.')
            for rules in registry.rules.values():
                rules.verify()
            result = reconcile_fund()
        except (RuntimeError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f'Casino verified: {json.dumps(result, sort_keys=True)}'))
