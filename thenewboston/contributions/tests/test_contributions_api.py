from model_bakery import baker
from pytest_parametrize_cases import Case, parametrize_cases

NO = object()
USER = object()
OTHER = object()


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
