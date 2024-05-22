from datetime import timedelta

from django.utils import timezone
from faker import Faker

from thenewboston.contributions.models.contribution import Contribution
from thenewboston.cores.models import Core
from thenewboston.general.commands import CustomCommand
from thenewboston.github.models.github_user import GitHubUser
# Assuming you have the following imports set up correctly
from thenewboston.github.models.issue import Issue
from thenewboston.github.models.pull import Pull
from thenewboston.github.models.repo import Repo
from thenewboston.users.models.user import User

fake = Faker()


def create_fake_contribution(n):
    for _ in range(n):
        core = Core.objects.order_by('?').first()
        github_user = GitHubUser.objects.order_by('?').first()
        issue = Issue.objects.order_by('?').first()
        pull = Pull.objects.order_by('?').first()
        repo = Repo.objects.order_by('?').first()
        user = User.objects.order_by('?').first()

        # Generate a random date between last month and this month
        today = timezone.now().date()
        start_date = today - timedelta(days=today.day)
        end_date = today
        random_date = fake.date_between(start_date=start_date, end_date=end_date)

        contribution = Contribution.objects.create(
            core=core,
            github_user=github_user,
            issue=issue,
            pull=pull,
            repo=repo,
            reward_amount=fake.random_number(digits=5),
            user=user
        )

        # Assuming Contribution model has 'created' and 'modified' fields
        contribution.created_date = random_date
        contribution.modified_date = random_date
        contribution.save()


class Command(CustomCommand):

    def handle(self, *args, **options):
        number_of_contributions = 300
        create_fake_contribution(number_of_contributions)
        print(f'Created {number_of_contributions} fake contributions.')
