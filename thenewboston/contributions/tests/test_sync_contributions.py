import pytest

from thenewboston.contributions.models import Contribution
from thenewboston.contributions.tasks import sync_contributions_task
from thenewboston.general.tests.vcr import assert_played, yield_cassette
from thenewboston.github.models import Pull
from thenewboston.wallets.models import Wallet

ASSESSMENT_EXPLANATION = (
    "This commit introduces substantial documentation improvements to the project's README file, "
    'significantly enhancing its usability and ease of understanding for both current and potential '
    'users and developers. By providing explicit HTTP request and Websocket interaction examples, '
    'the commit directly facilitates a more accessible and user-friendly guide for interacting with '
    "the application's API endpoints. Documentation like this is essential for effectively showcasing "
    "the application's capabilities, and supporting developers in integrating or contributing to the project. "
    'The detailed request and response examples reduce the learning curve for new users and developers, '
    'potentially speeding up development and debugging processes. This type of contribution is invaluable in '
    'open-source projects and in team-based development environments where clear communication and documentation '
    'can greatly accelerate progress and ease onboarding processes. Moreover, well-documented features are more '
    'likely to be used correctly and efficiently by end-users, boosting the software’s utility and reducing user '
    'frustration. This commit thus delivers significant value, not only in improving the project documentation '
    'but also in enhancing user experience and developer productivity.'
)


def test_sync_contributions(sample_repo, sample_github_user, sample_core):
    assert Pull.objects.count() == 0
    assert Contribution.objects.count() == 0
    assert Wallet.objects.count() == 0

    with (
        yield_cassette('sync_contributions.yaml') as cassette,
        assert_played(cassette, count=7),
    ):
        sync_contributions_task(limit=1)

    assert Pull.objects.count() == 1
    pull = Pull.objects.get()
    assert pull.repo == sample_repo
    assert pull.issue_number == 6
    assert pull.title == 'README updates'
    assert pull.description == 'Some README updates'
    assert pull.github_user == sample_github_user
    assert pull.assessment_points == 750
    assert pull.assessment_explanation == ASSESSMENT_EXPLANATION

    assert Contribution.objects.count() == 1
    contribution = Contribution.objects.get()
    assert contribution.contribution_type == 1  # ContributionType.PULL_REQUEST
    assert contribution.core == sample_core
    assert contribution.github_user == sample_github_user
    assert contribution.issue is None
    assert contribution.pull == pull
    assert contribution.repo == sample_repo
    assert contribution.user == sample_github_user.reward_recipient
    assert contribution.description == 'Some README updates'
    assert contribution.is_assessed()
    assert contribution.assessment_points == 750
    assert contribution.assessment_explanation == ASSESSMENT_EXPLANATION
    assert contribution.is_rewarded()
    assert contribution.reward_amount == 750

    assert Wallet.objects.count() == 1
    wallet = Wallet.objects.get()
    assert wallet.owner == sample_github_user.reward_recipient
    assert wallet.core == sample_core
    assert wallet.balance == 750
    assert wallet.deposit_account_number
    assert wallet.deposit_balance == 0
    assert wallet.deposit_signing_key


@pytest.mark.usefixtures('sample_repo')
def test_sync_contributions__no_github_user():
    assert Pull.objects.count() == 0
    assert Contribution.objects.count() == 0
    assert Wallet.objects.count() == 0

    with (
        yield_cassette('sync_contributions.yaml') as cassette,
        assert_played(cassette, count=3),
    ):
        sync_contributions_task(limit=1)

    assert Pull.objects.count() == 0
    assert Contribution.objects.count() == 0
    assert Wallet.objects.count() == 0


def test_sync_contributions__reward_recipient_not_set(sample_repo, sample_github_user):
    sample_github_user.reward_recipient = None
    sample_github_user.save()

    assert Pull.objects.count() == 0
    assert Contribution.objects.count() == 0
    assert Wallet.objects.count() == 0

    with (
        yield_cassette('sync_contributions.yaml') as cassette,
        assert_played(cassette, count=7),
    ):
        sync_contributions_task(limit=1)

    assert Pull.objects.count() == 1
    pull = Pull.objects.get()
    assert pull.repo == sample_repo
    assert pull.issue_number == 6
    assert pull.title == 'README updates'
    assert pull.description == 'Some README updates'
    assert pull.github_user == sample_github_user
    assert pull.assessment_points == 750
    assert pull.assessment_explanation == ASSESSMENT_EXPLANATION

    assert Contribution.objects.count() == 0
    assert Wallet.objects.count() == 0


def test_sync_contributions__no_core(sample_repo, sample_github_user):
    assert Pull.objects.count() == 0
    assert Contribution.objects.count() == 0
    assert Wallet.objects.count() == 0

    with (
        yield_cassette('sync_contributions.yaml') as cassette,
        assert_played(cassette, count=7),
    ):
        sync_contributions_task(limit=1)

    assert Pull.objects.count() == 1
    pull = Pull.objects.get()
    assert pull.repo == sample_repo
    assert pull.issue_number == 6
    assert pull.title == 'README updates'
    assert pull.description == 'Some README updates'
    assert pull.github_user == sample_github_user
    assert pull.assessment_points == 750
    assert pull.assessment_explanation == ASSESSMENT_EXPLANATION

    assert Contribution.objects.count() == 0
    assert Wallet.objects.count() == 0


def test_sync_contributions__wallet_already_exists(sample_repo, sample_github_user, sample_core):
    assert Pull.objects.count() == 0
    assert Contribution.objects.count() == 0
    assert Wallet.objects.count() == 0

    wallet, _ = Wallet.objects.get_or_create(
        core_id=sample_core.id, owner=sample_github_user.reward_recipient, defaults={'balance': 40}
    )

    with (
        yield_cassette('sync_contributions.yaml') as cassette,
        assert_played(cassette, count=7),
    ):
        sync_contributions_task(limit=1)

    assert Pull.objects.count() == 1
    pull = Pull.objects.get()
    assert pull.repo == sample_repo
    assert pull.issue_number == 6
    assert pull.title == 'README updates'
    assert pull.description == 'Some README updates'
    assert pull.github_user == sample_github_user
    assert pull.assessment_points == 750
    assert pull.assessment_explanation == ASSESSMENT_EXPLANATION

    assert Contribution.objects.count() == 1
    contribution = Contribution.objects.get()
    assert contribution.contribution_type == 1  # ContributionType.PULL_REQUEST
    assert contribution.core == sample_core
    assert contribution.github_user == sample_github_user
    assert contribution.issue is None
    assert contribution.pull == pull
    assert contribution.repo == sample_repo
    assert contribution.user == sample_github_user.reward_recipient
    assert contribution.description == 'Some README updates'
    assert contribution.is_assessed()
    assert contribution.assessment_points == 750
    assert contribution.assessment_explanation == ASSESSMENT_EXPLANATION
    assert contribution.is_rewarded()
    assert contribution.reward_amount == 750

    assert Wallet.objects.count() == 1
    wallet = Wallet.objects.get()
    assert wallet.owner == sample_github_user.reward_recipient
    assert wallet.core == sample_core
    assert wallet.balance == 790
    assert wallet.deposit_account_number
    assert wallet.deposit_balance == 0
    assert wallet.deposit_signing_key
