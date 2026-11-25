import json

from django.core.management.base import BaseCommand, CommandError

from thenewboston.casino.rules import RULES, SLOT_WEIGHTS
from thenewboston.casino.services import reconcile_fund


class Command(BaseCommand):
    help = 'Verify casino ledger, reservations, and installed payout rules without moving coins.'

    def handle(self, *args, **options):
        if sum(weight for _, weight in SLOT_WEIGHTS) != 10000:
            raise CommandError('Slot probabilities do not sum to 100%.')
        if sum(multiplier * weight for multiplier, weight in SLOT_WEIGHTS) != 9600:
            raise CommandError('Slot RTP is not 96%.')
        if max(multiplier for multiplier, _ in SLOT_WEIGHTS) != 100 or RULES[('slots', 1)].max_multiplier != 100:
            raise CommandError('Slot maximum payout is not 100x.')
        try:
            result = reconcile_fund()
        except RuntimeError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f'Casino verified: {json.dumps(result, sort_keys=True)}'))
