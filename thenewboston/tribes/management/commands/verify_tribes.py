import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q, Sum

from thenewboston.tribes.models import Tournament
from thenewboston.tribes.rules import BUILDINGS, DEFENSES, LAND, MAX_MEMBERS, RECIPES, UNITS


def verify_tournament(tournament):
    state = tournament.state
    tribes = state.get('tribes', [])
    listings = state.get('listings', [])
    participants = set(tournament.participants.values_list('user_id', flat=True))
    if len(participants) > tournament.max_players:
        raise CommandError(f'Tournament {tournament.pk}: roster exceeds capacity.')
    seen = set()
    for tribe in tribes:
        members = [member['id'] for member in tribe['members']]
        if not members or len(members) > MAX_MEMBERS or len(members) != len(set(members)):
            raise CommandError(f'Tournament {tournament.pk}: invalid tribe roster.')
        if seen.intersection(members) or not set(members).issubset(participants):
            raise CommandError(f'Tournament {tournament.pk}: duplicate or unenrolled tribe member.')
        if tribe['founder_id'] not in members:
            raise CommandError(f'Tournament {tournament.pk}: captain is not a tribe member.')
        seen.update(members)
    treasury = sum(tribe['treasury'] for tribe in tribes)
    escrow = sum(listing['quantity'] * listing['price'] for listing in listings if listing['kind'] == 'buy')
    reserve = tournament.total_deposited - tournament.total_withdrawn
    ledger = tournament.money_entries.aggregate(
        deposited=Sum('amount', filter=Q(amount__gt=0)),
        withdrawn=Sum('amount', filter=Q(amount__lt=0)),
    )
    if tournament.total_deposited != (ledger['deposited'] or 0) or tournament.total_withdrawn != -(
        ledger['withdrawn'] or 0
    ):
        raise CommandError(f'Tournament {tournament.pk}: wallet ledger does not match the reserve.')
    if reserve != treasury + escrow + tournament.system_revenue:
        raise CommandError(f'Tournament {tournament.pk}: TNB reserve is not conserved.')
    if any(tribe['treasury'] < 0 for tribe in tribes):
        raise CommandError(f'Tournament {tournament.pk}: a treasury is negative.')
    if any(listing['quantity'] < 0 or listing['price'] <= 0 for listing in listings):
        raise CommandError(f'Tournament {tournament.pk}: invalid market quantity or price.')
    if tournament.status == 'finished' and (treasury or escrow):
        raise CommandError(f'Tournament {tournament.pk}: unsettled TNB remains after the final battle.')
    if tournament.ends_at <= tournament.starts_at:
        raise CommandError(f'Tournament {tournament.pk}: invalid tournament deadline.')
    battle = state.get('battle')
    if battle:
        standings = battle['standings']
        if sum(row['outgoing'] for row in standings) != sum(row['incoming'] for row in standings):
            raise CommandError(f'Tournament {tournament.pk}: battle damage is not conserved.')
        if any(row['score'] != row['outgoing'] - row['incoming'] for row in standings):
            raise CommandError(f'Tournament {tournament.pk}: an incorrect battle score was recorded.')
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
            raise CommandError('The Tribes tournament and production sweep is not scheduled.')
        count, reserve = 0, 0
        # Lock one tournament at a time so each economic snapshot matches its immutable ledger.
        for tournament_id in Tournament.objects.order_by('id').values_list('id', flat=True).iterator():
            with transaction.atomic():
                tournament = Tournament.objects.select_for_update().get(pk=tournament_id)
                reserve += verify_tournament(tournament)
                count += 1
        self.stdout.write(
            self.style.SUCCESS(f'Tribes verified: {json.dumps({"tournaments": count, "tnb_reserve": reserve})}')
        )
