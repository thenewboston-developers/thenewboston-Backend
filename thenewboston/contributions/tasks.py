import logging

from celery import shared_task

from thenewboston.contributions.business_logic.process import process_repos
from thenewboston.contributions.business_logic.sync import sync_repos
from thenewboston.general.utils.misc import swallow_exception

logger = logging.getLogger(__name__)


@shared_task(name='tasks.sync_contributions')
def sync_contributions(repo_id=None, limit=None):
    swallow_exception(sync_repos, repo_id=repo_id, limit=limit)
    swallow_exception(process_repos, repo_id=repo_id, limit=limit)
