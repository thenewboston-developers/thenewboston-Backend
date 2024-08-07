from datetime import datetime
from unittest.mock import patch

from django.conf import settings
from freezegun import freeze_time
from model_bakery import baker
from pytest_parametrize_cases import Case, parametrize_cases

from thenewboston.contributions.models import Contribution
from thenewboston.contributions.models.contribution import ContributionType
from thenewboston.contributions.tasks import reward_manual_contributions_task
from thenewboston.cores.tests.fixtures.core import create_core
from thenewboston.cores.utils.core import get_default_core
from thenewboston.general.tests.vcr import assert_played, yield_cassette
from thenewboston.github.tests.fixtures.github_user import create_github_user
from thenewboston.github.tests.fixtures.issue import create_issue
from thenewboston.github.tests.fixtures.repo import create_repo
from thenewboston.wallets.models import Wallet

ASSESSMENT_EXPLANATION = (
    'The creation of 3 new designs in Figma can be a valuable contribution, particularly if these designs are '
    "intended to improve the user interface and user experience of our project's software components. "
    'Given that visual and interaction design can significantly impact the usability and appeal of our tools '
    "and platforms, your contribution is recognized as enhancing the project's appeal and potentially its "
    'functionality. However, without specific details on how these designs align with our milestones—such '
    'as improving your ability to submit PRs, interact with other AIs, or contribute more effectively to '
    'the project—the value assessment must be conservative. Further information on how these designs directly '
    'support our milestones or your development would likely increase the assessed value of this contribution.'
)
ABSENT = object()


def test_create_manual_contribution(authenticated_api_client):
    api_client = authenticated_api_client
    user = api_client.forced_user
    user.avatar = 'example-avatar.jpg'
    user.save()

    assert Contribution.objects.count() == 0
    assert Wallet.objects.count() == 0

    with (
        freeze_time('2024-05-17T07:00:00Z'), patch('thenewboston.contributions.tasks.reward_manual_contributions') as
        reward_manual_contributions_mock
    ):
        core = create_core(owner=user)

        assert settings.DEFAULT_CORE_TICKER == 'TNB'
        assert core.ticker == 'TNB'
        assert get_default_core() == core

        payload = {'description': 'I made 3 new designs in Figma'}
        response = api_client.post('/api/contributions', payload)

    assert response.status_code == 201
    response_json = response.json()
    contribution_id = response_json.get('id')
    assert isinstance(contribution_id, int)
    assert response_json == {
        'id': contribution_id,
        'contribution_type': 2,  # ContributionType.MANUAL
        'github_user': None,
        'issue': None,
        'pull': None,
        'reward_amount': None,
        'assessment_explanation': '',
        'assessment_points': None,
        'description': 'I made 3 new designs in Figma',
        'created_date': '2024-05-17T07:00:00Z',
        'modified_date': '2024-05-17T07:00:00Z',
        'repo': None,
        'user': {
            'avatar': 'http://testserver/media/example-avatar.jpg',
            'id': user.id,
            'is_manual_contribution_allowed': user.is_manual_contribution_allowed,
            'username': 'bucky'
        },
        'core': {
            'id': core.id,
            'created_date': '2024-05-17T07:00:00Z',
            'modified_date': '2024-05-17T07:00:00Z',
            'domain': 'thenewboston.net',
            'logo': None,
            'ticker': 'TNB',
            'owner': core.owner_id,
        },
    }

    reward_manual_contributions_mock.assert_called_once_with(contribution_id=contribution_id)

    assert Contribution.objects.count() == 1
    contribution = Contribution.objects.get()
    assert contribution.core == core
    assert contribution.contribution_type == 2  # ContributionType.MANUAL
    assert contribution.github_user is None
    assert contribution.issue is None
    assert contribution.pull is None
    assert contribution.repo is None
    assert contribution.user == user
    assert contribution.description == 'I made 3 new designs in Figma'
    assert not contribution.is_assessed()
    assert contribution.assessment_points is None
    assert contribution.assessment_explanation == ''
    assert not contribution.is_rewarded()
    assert contribution.rewarded_at is None
    assert contribution.reward_amount is None

    assert Wallet.objects.count() == 0

    with (
        freeze_time('2024-05-17T07:10:00Z'),
        yield_cassette('reward_manual_contributions.yaml') as cassette,
        assert_played(cassette, count=3),
    ):
        reward_manual_contributions_task(contribution_id=contribution_id)

    assert Contribution.objects.count() == 1
    contribution = Contribution.objects.get()
    assert contribution.core == core
    assert contribution.contribution_type == 2  # ContributionType.PULL_REQUEST
    assert contribution.github_user is None
    assert contribution.issue is None
    assert contribution.pull is None
    assert contribution.repo is None
    assert contribution.user == user
    assert contribution.description == 'I made 3 new designs in Figma'

    # Assert assessed and rewarded
    assert contribution.is_assessed()
    assert contribution.assessment_points == 500
    assert contribution.assessment_explanation == ASSESSMENT_EXPLANATION
    assert contribution.is_rewarded()
    assert contribution.rewarded_at == datetime.fromisoformat('2024-05-17T07:10:00+00:00')
    assert contribution.reward_amount == 500

    assert Wallet.objects.count() == 1
    wallet = Wallet.objects.get()
    assert wallet.owner == user
    assert wallet.core == core
    assert wallet.balance == 500
    assert wallet.deposit_account_number
    assert wallet.deposit_balance == 0
    assert wallet.deposit_signing_key

    pull_request_contribution = baker.make(
        'contributions.Contribution', contribution_type=ContributionType.PULL_REQUEST.value, reward_amount=None
    )
    rewarded_manual_contribution = baker.make(
        'contributions.Contribution', contribution_type=ContributionType.MANUAL.value, reward_amount=10
    )
    reward_manual_contributions_task()
    pull_request_contribution.refresh_from_db()
    assert pull_request_contribution.reward_amount is None

    rewarded_manual_contribution.refresh_from_db()
    assert rewarded_manual_contribution.reward_amount == 10


def test_create_manual_contribution__daily_limit(authenticated_api_client):
    api_client = authenticated_api_client
    user = api_client.forced_user
    user.manual_contribution_reward_daily_limit = 7
    user.save()

    assert Contribution.objects.count() == 0
    assert Wallet.objects.count() == 0

    with (
        freeze_time('2024-05-17T07:00:00Z'), patch('thenewboston.contributions.tasks.reward_manual_contributions') as
        reward_manual_contributions_mock
    ):
        core = create_core(owner=user)

        assert settings.DEFAULT_CORE_TICKER == 'TNB'
        assert core.ticker == 'TNB'
        assert get_default_core() == core

        payload = {'description': 'I made 3 new designs in Figma'}
        response = api_client.post('/api/contributions', payload)

    assert response.status_code == 201
    response_json = response.json()
    contribution_id = response_json.get('id')
    assert isinstance(contribution_id, int)
    reward_manual_contributions_mock.assert_called_once_with(contribution_id=contribution_id)

    assert Contribution.objects.count() == 1
    contribution = Contribution.objects.get()
    assert not contribution.is_assessed()
    assert contribution.assessment_points is None
    assert contribution.assessment_explanation == ''
    assert not contribution.is_rewarded()
    assert contribution.rewarded_at is None
    assert contribution.reward_amount is None

    assert Wallet.objects.count() == 0

    baker.make(
        'contributions.Contribution',
        contribution_type=2,
        rewarded_at=datetime.fromisoformat('2024-05-17T06:00:00+00:00'),
        reward_amount=2,
        user=user,
    )

    with (
        freeze_time('2024-05-17T07:10:00Z'),
        yield_cassette('reward_manual_contributions.yaml') as cassette,
        assert_played(cassette, count=3),
    ):
        reward_manual_contributions_task(contribution_id=contribution_id)

    contribution = Contribution.objects.get(id=contribution_id)
    assert contribution.is_assessed()
    assert contribution.assessment_points == 500
    assert contribution.assessment_explanation == ASSESSMENT_EXPLANATION
    assert contribution.is_rewarded()
    assert contribution.rewarded_at == datetime.fromisoformat('2024-05-17T07:10:00+00:00')
    assert contribution.reward_amount == 5

    assert Wallet.objects.count() == 1
    wallet = Wallet.objects.get()
    assert wallet.owner == user
    assert wallet.core == core
    assert wallet.balance == 5
    assert wallet.deposit_account_number
    assert wallet.deposit_balance == 0
    assert wallet.deposit_signing_key


def test_can_provide_optional_fields(sample_core, authenticated_api_client):
    core = sample_core

    assert settings.DEFAULT_CORE_TICKER == 'TNB'
    assert core.ticker == 'TNB'
    assert get_default_core() == core

    api_client = authenticated_api_client
    user = api_client.forced_user

    with freeze_time('2024-05-17T07:00:00Z'):
        github_user = create_github_user(user)

    assert Contribution.objects.count() == 0
    assert Wallet.objects.count() == 0

    # github_user
    payload = {
        'description': 'I made 3 new designs in Figma',
        'github_user': github_user.id,
    }
    with patch('thenewboston.contributions.tasks.reward_manual_contributions'):
        response = api_client.post('/api/contributions', payload)

    assert response.status_code == 201
    response_json = response.json()
    contribution_id = response_json.get('id')
    assert isinstance(contribution_id, int)
    assert response_json.get('github_user') == {
        'id': github_user.id,
        'reward_recipient': {
            'avatar': None,
            'is_manual_contribution_allowed': github_user.reward_recipient.is_manual_contribution_allowed,
            'id': github_user.reward_recipient_id,
            'username': 'bucky'
        },
        'created_date': '2024-05-17T07:00:00Z',
        'modified_date': '2024-05-17T07:00:00Z',
        'github_id': 8547538,
        'github_username': 'buckyroberts'
    }

    assert Contribution.objects.count() == 1
    contribution = Contribution.objects.get()
    assert contribution.github_user == github_user

    with freeze_time('2024-05-17T07:00:00Z'):
        repo = create_repo()

    payload = {
        'description': 'I made 3 new designs in Figma',
        'repo': repo.id,
    }
    with patch('thenewboston.contributions.tasks.reward_manual_contributions'):
        response = api_client.post('/api/contributions', payload)

    assert response.status_code == 201
    response_json = response.json()
    contribution_id = response_json.get('id')
    assert isinstance(contribution_id, int)
    assert response_json.get('repo') == {
        'id': repo.id,
        'created_date': '2024-05-17T07:00:00Z',
        'modified_date': '2024-05-17T07:00:00Z',
        'owner_name': 'thenewboston-developers',
        'name': 'Core',
        'contribution_branch': 'master'
    }

    contribution = Contribution.objects.get(id=contribution_id)
    assert contribution.repo == repo

    with freeze_time('2024-05-17T07:00:00Z'):
        issue = create_issue(repo)

    payload = {
        'description': 'I made 3 new designs in Figma',
        'issue': issue.id,
    }
    with patch('thenewboston.contributions.tasks.reward_manual_contributions'):
        response = api_client.post('/api/contributions', payload)

    assert response.status_code == 201
    response_json = response.json()
    contribution_id = response_json.get('id')
    assert isinstance(contribution_id, int)
    assert response_json.get('issue') == {
        'id': issue.id,
        'created_date': '2024-05-17T07:00:00Z',
        'modified_date': '2024-05-17T07:00:00Z',
        'issue_number': 1,
        'title': 'First issue',
        'repo': repo.id
    }

    contribution = Contribution.objects.get(id=contribution_id)
    assert contribution.issue == issue


@parametrize_cases(
    Case(
        '1',
        field='repo',
        value=1234567,
        expected_response={'repo': ['Invalid pk "1234567" - object does not exist.']}
    ),
    Case('2', field='description', value=ABSENT, expected_response={'description': ['This field is required.']}),
    Case('3', field='description', value=None, expected_response={'description': ['This field may not be null.']}),
    Case(
        '4',
        field='contribution_type',
        value=1,
        expected_response={'non_field_errors': ['Fixed field(s): contribution_type']}
    ),
    Case('5', field='id', value=10, expected_response={'non_field_errors': ['Readonly field(s): id']}),
    Case('6', field='pull', value=10, expected_response={'non_field_errors': ['Readonly field(s): pull']}),
    Case(
        '7',
        field='reward_amount',
        value=10,
        expected_response={'non_field_errors': ['Readonly field(s): reward_amount']}
    ),
    Case(
        '8',
        field='assessment_explanation',
        value='Great stuff',
        expected_response={'non_field_errors': ['Readonly field(s): assessment_explanation']}
    ),
    Case(
        '9',
        field='assessment_points',
        value=10,
        expected_response={'non_field_errors': ['Readonly field(s): assessment_points']}
    ),
    Case(
        '10',
        field='created_date',
        value='2024-05-17T07:00:00Z',
        expected_response={'non_field_errors': ['Readonly field(s): created_date']}
    ),
    Case(
        '11',
        field='modified_date',
        value='2024-05-17T07:00:00Z',
        expected_response={'non_field_errors': ['Readonly field(s): modified_date']}
    ),
    Case('12', field='user', value=10, expected_response={'non_field_errors': ['Fixed field(s): user']}),
    Case('13', field='core', value=20, expected_response={'non_field_errors': ['Fixed field(s): core']}),
)
def test_fields_optionality(sample_core, sample_repo, field, value, expected_response, authenticated_api_client):
    api_client = authenticated_api_client

    core = sample_core

    assert settings.DEFAULT_CORE_TICKER == 'TNB'
    assert core.ticker == 'TNB'
    assert get_default_core() == core

    repo = sample_repo

    assert Contribution.objects.count() == 0
    assert Wallet.objects.count() == 0

    payload = {'repo': repo.id, 'description': 'I made 3 new designs in Figma'}
    if value is ABSENT:
        del payload[field]
    else:
        payload[field] = value

    with patch('thenewboston.contributions.tasks.reward_manual_contributions'):
        response = api_client.post('/api/contributions', payload)

    assert response.status_code == 400
    assert response.json() == expected_response
    assert Contribution.objects.count() == 0
    assert Wallet.objects.count() == 0
