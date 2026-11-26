import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q, Sum

from thenewboston.tribes.models import Season
from thenewboston.tribes.rules import BUILDINGS, DEFENSES, LAND, RECIPES, UNITS


def verify_season(season):
    state = season.state
    tribes = state.get('tribes', [])
    listings = state.get('listings', [])
    treasury = sum(tribe['treasury'] for tribe in tribes)
    escrow = sum(listing['quantity'] * listing['price'] for listing in listings if listing['kind'] == 'buy')
    reserve = season.total_deposited - season.total_withdrawn
    ledger = season.money_entries.aggregate(
        deposited=Sum('amount', filter=Q(amount__gt=0)),
        withdrawn=Sum('amount', filter=Q(amount__lt=0)),
    )
    if season.total_deposited != (ledger['deposited'] or 0) or season.total_withdrawn != -(ledger['withdrawn'] or 0):
        raise CommandError(f'Season {season.pk}: wallet ledger does not match the reserve.')
    if reserve != treasury + escrow + season.system_revenue:
        raise CommandError(f'Season {season.pk}: TNB reserve is not conserved.')
    if any(tribe['treasury'] < 0 for tribe in tribes):
        raise CommandError(f'Season {season.pk}: a treasury is negative.')
    if any(listing['quantity'] < 0 or listing['price'] <= 0 for listing in listings):
        raise CommandError(f'Season {season.pk}: invalid market quantity or price.')
    if season.status == 'finished' and (treasury or escrow):
        raise CommandError(f'Season {season.pk}: unsettled TNB remains after the final battle.')
    if season.ends_at <= season.starts_at:
        raise CommandError(f'Season {season.pk}: invalid tournament deadline.')
    battle = state.get('battle')
    if battle:
        standings = battle['standings']
        if sum(row['outgoing'] for row in standings) != sum(row['incoming'] for row in standings):
            raise CommandError(f'Season {season.pk}: battle damage is not conserved.')
        if any(row['score'] != row['outgoing'] - row['incoming'] for row in standings):
            raise CommandError(f'Season {season.pk}: an incorrect battle score was recorded.')
    return reserve


class Command(BaseCommand):
    help = 'Verify Tribes rules, scheduler configuration, and TNB conservation without moving coins.'

    def handle(self, *args, **options):
        if (len(LAND), len(BUILDINGS), len(UNITS), len(DEFENSES)) != (6, 6, 3, 2):
            raise CommandError('The Tribes MVP catalog is incomplete.')
        for item in (*BUILDINGS, *UNITS, *DEFENSES):
            if item not in RECIPES or RECIPES[item]['seconds'] <= 0:
                raise CommandError(f'Missing or invalid recipe: {item}.')
        scheduled = [entry for entry in settings.CELERY_BEAT_SCHEDULE.values() if 'tribes' in entry['task']]
        if not scheduled:
            raise CommandError('The Tribes season and production sweep is not scheduled.')
        count, reserve = 0, 0
        # Lock one season at a time so each economic snapshot matches its immutable ledger.
        for season_id in Season.objects.order_by('id').values_list('id', flat=True).iterator():
            with transaction.atomic():
                season = Season.objects.select_for_update().get(pk=season_id)
                reserve += verify_season(season)
                count += 1
        self.stdout.write(
            self.style.SUCCESS(f'Tribes verified: {json.dumps({"seasons": count, "tnb_reserve": reserve})}')
        )
