import pytest
from django.test import override_settings

from thenewboston.contributions.models import Contribution
from thenewboston.contributions.tasks import sync_contributions
from thenewboston.general.tests.vcr import assert_played, yield_cassette
from thenewboston.github.models import Pull
from thenewboston.wallets.models import Wallet

ASSESSMENT_EXPLANATION = (
    "This change introduces substantial documentation improvements to the project's README file, "
    'significantly enhancing its usability and ease of understanding for both current and potential '
    'users and developers. By providing explicit examples of how to interact with the system via HTTP '
    'and WebSocket, it reduces the learning curve for new developers and increases the likelihood of '
    'correct usage by external systems. Curated documentation, especially including direct examples of '
    'requests and responses, is immensely valuable in software development as it serves as both a guide '
    'for new project participants and a reference material for existing users. This documentation addition '
    "arguably increases the project's value by making it more accessible, maintainable, and easier to "
    'integrate with, thus, impacting the overall usability and comprehensibility of the project positively.'
)


def test_sync_contributions(sample_repo, sample_github_user, sample_core):
    assert Pull.objects.count() == 0
    assert Contribution.objects.count() == 0
    assert Wallet.objects.count() == 0

    with (
        override_settings(GITHUB_PULL_REQUEST_STATE_FILTER='all'),
        yield_cassette('sync_contributions.yaml') as cassette,
        assert_played(cassette, count=7),
    ):
        sync_contributions(limit=1)

    assert Pull.objects.count() == 1
    pull = Pull.objects.get()
    assert pull.repo == sample_repo
    assert pull.issue_number == 6
    assert pull.title == 'README updates'
    assert pull.github_user == sample_github_user
    assert pull.assessment_points == 750
    assert pull.assessment_explanation == ASSESSMENT_EXPLANATION

    assert Contribution.objects.count() == 1
    contribution = Contribution.objects.get()
    assert contribution.core == sample_core
    assert contribution.github_user == sample_github_user
    assert contribution.issue is None
    assert contribution.pull == pull
    assert contribution.repo == sample_repo
    assert contribution.reward_amount == 750
    assert contribution.user == sample_github_user.reward_recipient
    assert contribution.explanation == ASSESSMENT_EXPLANATION

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
        override_settings(GITHUB_PULL_REQUEST_STATE_FILTER='all'),
        yield_cassette('sync_contributions.yaml') as cassette,
        assert_played(cassette, count=2),
    ):
        sync_contributions(limit=1)

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
        override_settings(GITHUB_PULL_REQUEST_STATE_FILTER='all'),
        yield_cassette('sync_contributions.yaml') as cassette,
        assert_played(cassette, count=7),
    ):
        sync_contributions(limit=1)

    assert Pull.objects.count() == 1
    pull = Pull.objects.get()
    assert pull.repo == sample_repo
    assert pull.issue_number == 6
    assert pull.title == 'README updates'
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
        override_settings(GITHUB_PULL_REQUEST_STATE_FILTER='all'),
        yield_cassette('sync_contributions.yaml') as cassette,
        assert_played(cassette, count=7),
    ):
        sync_contributions(limit=1)

    assert Pull.objects.count() == 1
    pull = Pull.objects.get()
    assert pull.repo == sample_repo
    assert pull.issue_number == 6
    assert pull.title == 'README updates'
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
        override_settings(GITHUB_PULL_REQUEST_STATE_FILTER='all'),
        yield_cassette('sync_contributions.yaml') as cassette,
        assert_played(cassette, count=7),
    ):
        sync_contributions(limit=1)

    assert Pull.objects.count() == 1
    pull = Pull.objects.get()
    assert pull.repo == sample_repo
    assert pull.issue_number == 6
    assert pull.title == 'README updates'
    assert pull.github_user == sample_github_user
    assert pull.assessment_points == 750
    assert pull.assessment_explanation == ASSESSMENT_EXPLANATION

    assert Contribution.objects.count() == 1
    contribution = Contribution.objects.get()
    assert contribution.core == sample_core
    assert contribution.github_user == sample_github_user
    assert contribution.issue is None
    assert contribution.pull == pull
    assert contribution.repo == sample_repo
    assert contribution.reward_amount == 750
    assert contribution.user == sample_github_user.reward_recipient
    assert contribution.explanation == ASSESSMENT_EXPLANATION

    assert Wallet.objects.count() == 1
    wallet = Wallet.objects.get()
    assert wallet.owner == sample_github_user.reward_recipient
    assert wallet.core == sample_core
    assert wallet.balance == 790
    assert wallet.deposit_account_number
    assert wallet.deposit_balance == 0
    assert wallet.deposit_signing_key
