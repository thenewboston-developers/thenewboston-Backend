from datetime import datetime
from unittest.mock import patch

from freezegun import freeze_time
from model_bakery import baker
from pytest_parametrize_cases import Case, parametrize_cases

from thenewboston.contributions.models import Contribution
from thenewboston.contributions.models.contribution import ContributionType
from thenewboston.contributions.tasks import reward_manual_contributions_task
from thenewboston.cores.tests.fixtures.core import create_core
from thenewboston.general.tests.vcr import assert_played, yield_cassette
from thenewboston.github.tests.fixtures.github_user import create_github_user
from thenewboston.github.tests.fixtures.issue import create_issue
from thenewboston.github.tests.fixtures.repo import create_repo
from thenewboston.wallets.models import Wallet

ASSESSMENT_EXPLANATION = (
    "As an AI developed by OpenAI, I'm not equipped with the capacity to directly view, access, or "
    'assess visual designs such as those created in Figma. My functionality is centered around processing '
    'text-based input and generating text-based output. Therefore, I cannot directly evaluate the quality, '
    'creativity, or impact of your Figma designs. Assessment of visual design work requires subjective '
    'analysis and consideration of aesthetic principles, design innovation, usability, and how effectively '
    'the design communicates its intended message or function. These nuances are best evaluated by humans or '
    'specialized software designed for visual design critique and analysis. However, creating new designs in '
    'Figma can be a valuable contribution to projects requiring visual communication, user interface design, '
    'or user experience enhancements, suggesting a non-zero intrinsic value in contexts where such '
    'contributions are applicable.'
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
        payload = {'core': core.id, 'description': 'I made 3 new designs in Figma'}
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
        assert_played(cassette, count=4),
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
    assert contribution.assessment_points == 9
    assert contribution.assessment_explanation == ASSESSMENT_EXPLANATION
    assert contribution.is_rewarded()
    assert contribution.rewarded_at == datetime.fromisoformat('2024-05-17T07:10:00+00:00')
    assert contribution.reward_amount == 9

    assert Wallet.objects.count() == 1
    wallet = Wallet.objects.get()
    assert wallet.owner == user
    assert wallet.core == core
    assert wallet.balance == 9
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
        payload = {'core': core.id, 'description': 'I made 3 new designs in Figma'}
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
        assert_played(cassette, count=4),
    ):
        reward_manual_contributions_task(contribution_id=contribution_id)

    contribution = Contribution.objects.get(id=contribution_id)
    assert contribution.is_assessed()
    assert contribution.assessment_points == 9
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
    api_client = authenticated_api_client
    user = api_client.forced_user
    core = sample_core

    with freeze_time('2024-05-17T07:00:00Z'):
        github_user = create_github_user(user)

    assert Contribution.objects.count() == 0
    assert Wallet.objects.count() == 0

    # github_user
    payload = {
        'core': core.id,
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
        'core': core.id,
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
        'core': core.id,
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
    Case('2', field='core', value=ABSENT, expected_response={'core': ['This field is required.']}),
    Case(
        '3',
        field='core',
        value=1234567,
        expected_response={'core': ['Invalid pk "1234567" - object does not exist.']}
    ),
    Case('4', field='core', value=None, expected_response={'core': ['This field may not be null.']}),
    Case('5', field='core', value='', expected_response={'core': ['This field may not be null.']}),
    Case('6', field='description', value=ABSENT, expected_response={'description': ['This field is required.']}),
    Case('7', field='description', value=None, expected_response={'description': ['This field may not be null.']}),
    Case(
        '8',
        field='contribution_type',
        value=1,
        expected_response={'non_field_errors': ['Fixed field(s): contribution_type']}
    ),
    Case('9', field='id', value=10, expected_response={'non_field_errors': ['Readonly field(s): id']}),
    Case('10', field='pull', value=10, expected_response={'non_field_errors': ['Readonly field(s): pull']}),
    Case(
        '11',
        field='reward_amount',
        value=10,
        expected_response={'non_field_errors': ['Readonly field(s): reward_amount']}
    ),
    Case(
        '12',
        field='assessment_explanation',
        value='Great stuff',
        expected_response={'non_field_errors': ['Readonly field(s): assessment_explanation']}
    ),
    Case(
        '13',
        field='assessment_points',
        value=10,
        expected_response={'non_field_errors': ['Readonly field(s): assessment_points']}
    ),
    Case(
        '14',
        field='created_date',
        value='2024-05-17T07:00:00Z',
        expected_response={'non_field_errors': ['Readonly field(s): created_date']}
    ),
    Case(
        '15',
        field='modified_date',
        value='2024-05-17T07:00:00Z',
        expected_response={'non_field_errors': ['Readonly field(s): modified_date']}
    ),
    Case('16', field='user', value=10, expected_response={'non_field_errors': ['Fixed field(s): user']}),
)
def test_fields_optionality(sample_core, sample_repo, field, value, expected_response, authenticated_api_client):
    api_client = authenticated_api_client

    core = sample_core
    repo = sample_repo

    assert Contribution.objects.count() == 0
    assert Wallet.objects.count() == 0

    payload = {'core': core.id, 'repo': repo.id, 'description': 'I made 3 new designs in Figma'}
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
