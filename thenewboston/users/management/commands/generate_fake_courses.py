import random

import requests
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from faker import Faker

from thenewboston.university.models.base import PublicationStatus
from thenewboston.university.models.course import Course
from thenewboston.university.models.lecture import Lecture


class Command(BaseCommand):
    description = 'Populates the database with random courses and lectures'

    def handle(self, *args, **options):
        faker = Faker()
        NUMBER_OF_COURSES = 100
        NUMBER_OF_LECTURES = 50
        thumbnail_urls = [
            'https://s3.amazonaws.com/thenewboston.network/images/2e61daf1-e939-4d45-af40-57b375fbd565.png',
            'https://s3.amazonaws.com/thenewboston.network/images/18d299a0-64ce-461d-ae15-8578c5cfff33.png',
            'https://s3.amazonaws.com/thenewboston.network/images/786f4e61-96f3-4b50-b6f8-858a6c3baef0.png',
            'https://s3.amazonaws.com/thenewboston.network/images/4ece7fe7-1f2c-44dc-ac17-444c60751874.png',
            'https://s3.amazonaws.com/thenewboston.network/images/a8e665a5-2dee-49dc-a0b7-d5ce0d0d5f52.png',
        ]
        user_model = get_user_model()
        instructor = user_model.objects.order_by('?').first()

        if not instructor:
            print('No users found in the database. Please create a user first.')
            return

        # Downloading the course thumbnail
        response = requests.get(random.choice(thumbnail_urls))
        if response.status_code == 200:
            course_thumbnail = ContentFile(response.content)
        else:
            print('Failed to download course thumbnail.')
            return

        for _ in range(NUMBER_OF_COURSES):
            course = Course(
                name=faker.sentence(nb_words=5),
                description=faker.text(max_nb_chars=200),
                publication_status=PublicationStatus.PUBLISHED,
                instructor=instructor
            )
            course.thumbnail.save(f'{faker.word()}.jpg', course_thumbnail, save=True)

            for _ in range(random.randint(10, NUMBER_OF_LECTURES)):
                Lecture.objects.create(
                    name=faker.sentence(nb_words=5),
                    description=faker.text(max_nb_chars=200),
                    publication_status=PublicationStatus.PUBLISHED,
                    course=course,
                    youtube_id=faker.bothify(text='???########'),
                    position=random.randint(1, 100),
                    thumbnail_url=random.choice(thumbnail_urls),
                )

        print('Database has been populated with courses and lectures.')
