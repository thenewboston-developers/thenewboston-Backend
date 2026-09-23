import pytest
from model_bakery import baker


@pytest.mark.django_db
@pytest.mark.parametrize('row_count', [1, 4])
@pytest.mark.parametrize('endpoint', ['wallets', 'user-wallets'])
def test_wallet_lists_have_constant_query_counts(
    authenticated_api_client, bucky, django_assert_num_queries, endpoint, row_count
):
    expected_wallets = {}
    for index in range(row_count):
        currency_owner = baker.make('users.User')
        elo = 1200 + index if index % 2 == 0 else None
        if elo is not None:
            baker.make('connect_five.ConnectFiveStats', user=currency_owner, elo=elo)
        currency = baker.make('currencies.Currency', owner=currency_owner)
        wallet = baker.make('wallets.Wallet', currency=currency, owner=bucky, balance=100 + index)
        baker.make('wallets.Wallet', currency=currency, owner=currency_owner, balance=200 + index)
        expected_wallets[wallet.id] = (currency.id, currency_owner.id, elo, wallet.balance)

    url = '/api/wallets' if endpoint == 'wallets' else f'/api/user-wallets/{bucky.id}'
    # Request savepoints and results, plus pagination count or the requested user lookup.
    with django_assert_num_queries(4):
        response = authenticated_api_client.get(url)

    assert response.status_code == 200
    data = response.json()
    rows = data['results'] if endpoint == 'wallets' else data
    assert len(rows) == row_count
    assert {
        row['id']: (
            row['currency']['id'],
            row['currency']['owner']['id'],
            row['currency']['owner']['connect_five_elo'],
            row['balance'],
        )
        for row in rows
    } == expected_wallets
    if endpoint == 'wallets':
        assert data['count'] == row_count
        assert all(row['owner'] == bucky.id for row in rows)
    else:
        assert all(row['rank'] == 2 and row['total_users'] == 2 and not row['is_owner'] for row in rows)


@pytest.mark.django_db
@pytest.mark.parametrize('row_count', [1, 4])
def test_transfer_list_has_constant_query_count(authenticated_api_client, bucky, django_assert_num_queries, row_count):
    currency = baker.make('currencies.Currency')
    expected_transfers = {}
    for index in range(row_count):
        for transfer_type in ('sent_post', 'received_post', 'sent_comment', 'received_comment'):
            counterparty = baker.make('users.User')
            elo = 1200 + index if index % 2 == 0 else None
            if elo is not None:
                baker.make('connect_five.ConnectFiveStats', user=counterparty, elo=elo)

            if transfer_type.endswith('post'):
                is_sent = transfer_type == 'sent_post'
                post = baker.make(
                    'social.Post',
                    owner=bucky if is_sent else counterparty,
                    recipient=counterparty if is_sent else bucky,
                    price_amount=10,
                    price_currency=currency,
                )
                key = (post.id, None)
            else:
                is_sent = transfer_type == 'sent_comment'
                post = baker.make('social.Post', owner=counterparty if is_sent else bucky)
                comment = baker.make(
                    'social.Comment',
                    owner=bucky if is_sent else counterparty,
                    post=post,
                    price_amount=10,
                    price_currency=currency,
                )
                key = (post.id, comment.id)

            expected_transfers[key] = (counterparty.id, elo, -10 if is_sent else 10)

    # Request savepoints plus one query each for posts, sent comments, and received comments.
    with django_assert_num_queries(5):
        response = authenticated_api_client.get('/api/transfers', {'currency': currency.id, 'page_size': 100})

    assert response.status_code == 200
    data = response.json()
    assert data['count'] == 4 * row_count
    assert len(data['results']) == 4 * row_count
    assert {
        (row['post_id'], row['comment_id']): (
            row['counterparty']['id'],
            row['counterparty']['connect_five_elo'],
            row['amount'],
        )
        for row in data['results']
    } == expected_transfers
    assert all(row['currency'] == currency.id for row in data['results'])
