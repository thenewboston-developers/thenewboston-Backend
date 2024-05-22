from random import choice

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from thenewboston.social.models.follower import Follower


class Command(BaseCommand):
    description = 'Create random followers and followings for the user with ID 4'

    def handle(self, *args, **options):
        User = get_user_model()

        target_user_id = 4
        num_relationships = 20

        if not User.objects.filter(id=target_user_id).exists():
            raise CommandError(f'User with ID {target_user_id} does not exist')

        user_ids = list(User.objects.exclude(id=target_user_id).values_list('id', flat=True))
        if not user_ids:
            raise CommandError('Not enough users to create relationships')

        created_count = 0

        for _ in range(num_relationships):
            with transaction.atomic():  # Handle each creation attempt in its own transaction
                try:
                    follower_id = choice(user_ids)
                    following_id = choice(user_ids)

                    # Ensure we do not create a following relationship with oneself
                    if follower_id == following_id:
                        continue

                    # Check if the follower relationship already exists
                    if Follower.objects.filter(follower_id=follower_id, following_id=following_id).exists():
                        continue

                    Follower.objects.create(follower_id=follower_id, following_id=following_id)
                    created_count += 1
                except Exception as e:
                    self.stderr.write(self.style.ERROR(f'Failed to create relationship: {str(e)}'))

        self.stdout.write(
            self.style.
            SUCCESS(f'Successfully created {created_count} relationships for user with ID {target_user_id}')
        )
