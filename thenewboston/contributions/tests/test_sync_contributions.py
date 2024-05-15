import pytest

from thenewboston.contributions.models import Contribution
from thenewboston.contributions.tasks import sync_contributions_task
from thenewboston.general.tests.vcr import assert_played, yield_cassette
from thenewboston.github.models import Pull
from thenewboston.wallets.models import Wallet

ASSESSMENT_EXPLANATION = (
    "This change introduces comprehensive examples for a blockchain service's API in the documentation, "
    "which significantly enhances the project's usability and accessibility for developers. By providing clear, "
    'working examples of how to interact with the API, including both HTTP and WebSocket interactions, '
    'it substantially lowers the barrier to entry for developers looking to integrate with or build upon '
    'this service. The examples cover not only the request format but also the expected responses, '
    'facilitating a smoother development process and reducing the scope for misunderstandings. '
    "Furthermore, the inclusion of 'payload' with a casual message in the examples subtly encourages "
    'experimentation, making the documentation not only useful but also engaging. '
    'This sort of documentation is invaluable for open-source projects, as it directly impacts '
    'the developer experience, potentially increasing adoption and contribution rates. Given the detailed '
    'nature of these examples and their potential to significantly assist developers, '
    'this change is assessed as highly valuable.'
)


def test_sync_contributions(sample_repo, sample_github_user, sample_core):
    assert Pull.objects.count() == 0
    assert Contribution.objects.count() == 0
    assert Wallet.objects.count() == 0

    with (
        yield_cassette('sync_contributions.yaml') as cassette,
        assert_played(cassette, count=8),
    ):
        sync_contributions_task(limit=1)

    assert Pull.objects.count() == 1
    pull = Pull.objects.get()
    assert pull.repo == sample_repo
    assert pull.issue_number == 6
    assert pull.title == 'README updates'
    assert pull.description == 'Closes x'
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
    assert contribution.description == 'Closes x'
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
        assert_played(cassette, count=8),
    ):
        sync_contributions_task(limit=1)

    assert Pull.objects.count() == 1
    pull = Pull.objects.get()
    assert pull.repo == sample_repo
    assert pull.issue_number == 6
    assert pull.title == 'README updates'
    assert pull.description == 'Closes x'
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
        assert_played(cassette, count=8),
    ):
        sync_contributions_task(limit=1)

    assert Pull.objects.count() == 1
    pull = Pull.objects.get()
    assert pull.repo == sample_repo
    assert pull.issue_number == 6
    assert pull.title == 'README updates'
    assert pull.description == 'Closes x'
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
        assert_played(cassette, count=8),
    ):
        sync_contributions_task(limit=1)

    assert Pull.objects.count() == 1
    pull = Pull.objects.get()
    assert pull.repo == sample_repo
    assert pull.issue_number == 6
    assert pull.title == 'README updates'
    assert pull.description == 'Closes x'
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
    assert contribution.description == 'Closes x'
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
