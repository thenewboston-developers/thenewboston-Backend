import random

from faker import Faker

from thenewboston.art.models.artwork import Artwork
from thenewboston.cores.models import Core
from thenewboston.general.commands import CustomCommand
from thenewboston.users.models.user import User

fake = Faker()


def create_fake_artkwork(num):
    for _ in range(num):
        creator = random.choice(User.objects.all())
        owner = random.choice(User.objects.all())
        core = random.choice(Core.objects.all()) if Core.objects.exists() else None

        name = fake.word().capitalize() + ' ' + fake.word().capitalize()
        description = fake.text()
        image_path = 'images/actually.jpg'
        image_url = fake.image_url()

        price_amount = random.choice([None, fake.random_number(digits=5)])

        artwork = Artwork(
            creator=creator,
            description=description,
            image=image_path,
            image_url=image_url,
            name=name,
            owner=owner,
            price_amount=price_amount,
            price_core=core,
        )
        artwork.save()


class Command(CustomCommand):

    def handle(self, *args, **options):
        num = 300
        create_fake_artkwork(num)
        print(f'Created {num} fake Artworks.')
