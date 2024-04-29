from django.db import transaction

from thenewboston.general.utils.misc import identity_decorator
from thenewboston.general.utils.pytest import is_pytest_running
from thenewboston.github.models import Repo

transaction_atomic = identity_decorator if is_pytest_running() else transaction.atomic


def get_repos(repo_id):
    query = Repo.objects.all()
    if repo_id is not None:
        query = query.filter(id=repo_id)

    return query.all()
