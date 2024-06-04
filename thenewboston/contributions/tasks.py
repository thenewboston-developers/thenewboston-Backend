import logging

from celery import shared_task

from thenewboston.contributions.business_logic.process import process_repos, reward_manual_contributions
from thenewboston.contributions.business_logic.sync import sync_repos
from thenewboston.general.utils.misc import swallow_exception

logger = logging.getLogger(__name__)


@shared_task(name='tasks.sync_contributions')
def sync_contributions_task(repo_id=None, limit=None):
    # We swallow exceptions to avoid duplicate logging, since it is logged with @log() decorator
    swallow_exception(sync_repos, repo_id=repo_id, limit=limit)
    swallow_exception(process_repos, repo_id=repo_id, limit=limit)


@shared_task(name='tasks.reward_manual_contributions')
def reward_manual_contributions_task(contribution_id=None):
    # We swallow exceptions to avoid duplicate logging, since it is logged with @log() decorator
    swallow_exception(reward_manual_contributions, contribution_id=contribution_id)
