from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from faker import Faker


class Command(BaseCommand):
    description = 'Creates multiple users with no avatars using Faker'

    def handle(self, *args, **options):
        User = get_user_model()
        fake = Faker()

        num_users = 300
        created_count = 0

        for _ in range(num_users):
            username = fake.user_name()
            email = fake.email()
            password = fake.password()

            try:
                user = User.objects.create_user(username=username, email=email, password=password)
                user.avatar = None  # Explicitly setting avatar to None
                user.save()
                self.stdout.write(self.style.SUCCESS(f'Successfully created user {user.username}'))
                created_count += 1
            except Exception as e:
                self.stderr.write(self.style.ERROR(f'Error creating user {username}: {str(e)}'))

        self.stdout.write(self.style.SUCCESS(f'Total users created: {created_count}'))
