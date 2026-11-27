from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from thenewboston.tribes.models import Season
from thenewboston.tribes.services import _advance, _lock_world


class Command(BaseCommand):
    help = 'Start the specified current recruiting Tribes season early, preserving its playing duration.'

    def add_arguments(self, parser):
        parser.add_argument('--season-id', type=int, required=True)

    def handle(self, *args, **options):
        with transaction.atomic():
            _lock_world()
            season = Season.objects.select_for_update().order_by('-id').first()
            if season is None or season.pk != options['season_id']:
                raise CommandError('The requested season is not the current Tribes season.')
            now = timezone.now()
            if season.status == 'finished' or now >= season.ends_at:
                raise CommandError('This season has ended and cannot be started again.')
            if season.status == 'active':
                message = f'Season {season.pk} is already active; its schedule and gameplay are unchanged.'
            else:
                tribes = season.state['tribes']
                if not tribes or any(not tribe['members'] for tribe in tribes):
                    raise CommandError('The season must have at least one tribe, with members in every tribe.')
                if any(season.state[key] for key in ('plots', 'jobs', 'units', 'listings', 'battle')):
                    raise CommandError(
                        'The recruiting season already contains gameplay; refusing to initialize it again.'
                    )
                if now < season.starts_at:
                    duration = season.ends_at - season.starts_at
                    season.starts_at = now
                    season.ends_at = now + duration
                _advance(season, now)
                message = f'Started Tribes season {season.pk}; rosters are now locked.'
        self.stdout.write(self.style.SUCCESS(message))
        self.stdout.write(f'Starts: {season.starts_at.isoformat()} | Ends: {season.ends_at.isoformat()}')
