import random

import requests
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from faker import Faker

from thenewboston.social.models.post import Post


class Command(BaseCommand):
    description = 'Populates the database with random posts'

    def handle(self, *args, **options):
        faker = Faker()
        NUMBER_OF_POSTS = 100
        thumbnail_urls = [
            'https://s3.amazonaws.com/thenewboston.network/images/2e61daf1-e939-4d45-af40-57b375fbd565.png',
            'https://s3.amazonaws.com/thenewboston.network/images/18d299a0-64ce-461d-ae15-8578c5cfff33.png',
            'https://s3.amazonaws.com/thenewboston.network/images/786f4e61-96f3-4b50-b6f8-858a6c3baef0.png',
            'https://s3.amazonaws.com/thenewboston.network/images/4ece7fe7-1f2c-44dc-ac17-444c60751874.png',
            'https://s3.amazonaws.com/thenewboston.network/images/a8e665a5-2dee-49dc-a0b7-d5ce0d0d5f52.png',
        ]
        user_model = get_user_model()
        owner = user_model.objects.order_by('?').first()

        if not owner:
            print('No users found in the database. Please create a user first.')
            return

        # Downloading the post image
        response = requests.get(random.choice(thumbnail_urls))
        if response.status_code == 200:
            image = ContentFile(response.content)
        else:
            print('Failed to download post image.')
            return

        for _ in range(NUMBER_OF_POSTS):
            post = Post(
                owner=owner,
                content=faker.text(max_nb_chars=200),
            )
            post.image.save(f'{faker.word()}.jpg', image, save=True)

        print('Database has been populated with posts.')
