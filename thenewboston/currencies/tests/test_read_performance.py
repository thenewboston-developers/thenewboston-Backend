import pytest
from model_bakery import baker


@pytest.mark.django_db
@pytest.mark.parametrize('row_count', [1, 4])
@pytest.mark.parametrize('endpoint', ['currencies', 'whitepapers', 'currency-balances'])
def test_currency_lists_have_constant_query_counts(
    authenticated_api_client, django_assert_num_queries, endpoint, row_count
):
    balance_currency = baker.make('currencies.Currency') if endpoint == 'currency-balances' else None
    expected_owners = {}

    for index in range(row_count):
        owner = baker.make('users.User')
        elo = 1200 + index if index % 2 == 0 else None
        if elo is not None:
            baker.make('connect_five.ConnectFiveStats', user=owner, elo=elo)
        expected_owners[owner.id] = elo

        if endpoint == 'currency-balances':
            baker.make('wallets.Wallet', currency=balance_currency, owner=owner, balance=100 + index)
        else:
            currency = baker.make('currencies.Currency', owner=owner)
            if endpoint == 'whitepapers':
                baker.make('currencies.Whitepaper', currency=currency, owner=owner, content=f'Whitepaper {index}')

    params = {'currency': balance_currency.id} if balance_currency else {}
    # Request savepoints, pagination count/results, and the minted-total aggregate for balances.
    with django_assert_num_queries(5 if balance_currency else 4):
        response = authenticated_api_client.get(f'/api/{endpoint}', params)

    assert response.status_code == 200
    data = response.json()
    assert data['count'] == row_count
    assert len(data['results']) == row_count
    assert {row['owner']['id']: row['owner']['connect_five_elo'] for row in data['results']} == expected_owners

    if balance_currency:
        assert [row['balance'] for row in data['results']] == list(reversed(range(100, 100 + row_count)))
        assert [row['rank'] for row in data['results']] == list(range(1, row_count + 1))
        assert all(row['percentage'] == 0 for row in data['results'])
