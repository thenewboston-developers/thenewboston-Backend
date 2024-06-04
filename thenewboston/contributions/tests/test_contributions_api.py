from freezegun import freeze_time
from model_bakery import baker
from pytest_parametrize_cases import Case, parametrize_cases

from thenewboston.contributions.models import Contribution
from thenewboston.cores.tests.fixtures.core import create_core
from thenewboston.github.tests.fixtures.github_user import create_github_user
from thenewboston.github.tests.fixtures.repo import create_repo

NO = object()
USER = object()
OTHER = object()


def test_get_contributions(authenticated_api_client):
    assert Contribution.objects.count() == 0

    user = authenticated_api_client.forced_user
    user.avatar = 'example-avatar.jpg'
    user.save()

    with freeze_time('2024-05-17T07:00:00Z'):
        core = create_core(owner=user)
        repo = create_repo()
        github_user = create_github_user(reward_recipient=user)
        contribution = baker.make(
            'contributions.Contribution',
            user=user,
            core=core,
            repo=repo,
            contribution_type=2,
            github_user=github_user,
            assessment_explanation='Sample explanation',
            reward_amount=10,
            assessment_points=20,
        )

    response = authenticated_api_client.get(f'/api/contributions/{contribution.id}')

    assert response.status_code == 200
    expected_response_json = {
        'id': contribution.id,
        'contribution_type': 2,
        'github_user': {
            'id': github_user.id,
            'github_id': 8547538,
            'github_username': 'buckyroberts',
            'created_date': '2024-05-17T07:00:00Z',
            'modified_date': '2024-05-17T07:00:00Z',
            'reward_recipient': {
                'id': github_user.reward_recipient_id,
                'is_manual_contribution_allowed': github_user.reward_recipient.is_manual_contribution_allowed,
                'avatar': 'http://testserver/media/example-avatar.jpg',
                'username': 'bucky'
            }
        },
        # TODO(dmu) MEDIUM: Improve assertions for `issue` and `pull`
        'issue': None,
        'pull': None,
        'reward_amount': 10,
        'assessment_explanation': 'Sample explanation',
        'assessment_points': 20,
        'description': '',
        'created_date': '2024-05-17T07:00:00Z',
        'modified_date': '2024-05-17T07:00:00Z',
        'repo': {
            'id': repo.id,
            'created_date': '2024-05-17T07:00:00Z',
            'modified_date': '2024-05-17T07:00:00Z',
            'owner_name': 'thenewboston-developers',
            'name': 'Core',
            'contribution_branch': 'master'
        },
        'user': {
            'id': user.id,
            'is_manual_contribution_allowed': user.is_manual_contribution_allowed,
            'avatar': 'http://testserver/media/example-avatar.jpg',
            'username': 'bucky'
        },
        'core': {
            'id': core.id,
            'created_date': '2024-05-17T07:00:00Z',
            'modified_date': '2024-05-17T07:00:00Z',
            'domain': 'thenewboston.net',
            # TODO(dmu) LOW: Improve assertion for `logo`
            'logo': None,
            'ticker': 'TNB',
            'owner': core.owner_id
        }
    }
    assert response.json() == expected_response_json

    response = authenticated_api_client.get('/api/contributions')
    assert response.status_code == 200
    assert response.json() == [expected_response_json]


@parametrize_cases(
    Case(user_id=NO, expected_len=5),
    Case(user_id=USER, expected_len=2),
    Case(user_id='me', expected_len=2),
    Case(user_id='self', expected_len=2),
    Case(user_id=OTHER, expected_len=3),
    Case(user_id='invalid', expected_len=0),
)
def test_contribution_filter(user_id, expected_len, authenticated_api_client):
    user = authenticated_api_client.forced_user
    other_user = baker.make('users.User')
    baker.make('contributions.Contribution', user=user, _quantity=2)
    baker.make('contributions.Contribution', user=other_user, _quantity=3)

    if user_id is NO:
        url = '/api/contributions'
    else:
        if user_id is USER:
            user_id = user.id
        elif user_id is OTHER:
            user_id = other_user.id
        url = f'/api/contributions?user_id={user_id}'

    response = authenticated_api_client.get(url)

    if user_id == 'invalid':
        assert response.status_code == 400
        assert response.json() == {'user_id': 'must be integer or one of me, self'}
    else:
        assert response.status_code == 200
        response_json = response.json()
        assert len(response_json) == expected_len
        if user_id is not NO:
            if user_id in {'me', 'self'}:
                user_id = user.id
            assert all(contribution['user']['id'] == user_id for contribution in response_json)
