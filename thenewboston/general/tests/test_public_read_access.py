from types import SimpleNamespace

import pytest
from model_bakery import baker

from thenewboston.connect_five.models import ConnectFiveChatMessage, ConnectFiveMatchPlayer, ConnectFiveStats
from thenewboston.connect_five.tests.test_read_query_counts import create_challenge, create_match
from thenewboston.exchange.tests.factories.exchange_order import make_buy_order
from thenewboston.general.constants import ANONYMOUS_MAX_PAGE_SIZE


@pytest.fixture
def content(bucky, dmitry, tnb_currency, yyy_currency, dmitry_tnb_wallet):
    post = baker.make('social.Post', owner=bucky, image='')
    comment = baker.make('social.Comment', post=post, owner=dmitry)
    baker.make('social.PostLike', post=post, user=dmitry)
    baker.make('social.Follower', follower=dmitry, following=bucky)

    baker.make('currencies.Mint', currency=yyy_currency, owner=bucky, amount=500)
    whitepaper = baker.make('currencies.Whitepaper', currency=yyy_currency, owner=bucky, content='# YYY')
    baker.make('wallets.Wallet', owner=dmitry, currency=yyy_currency, balance=250)

    order = make_buy_order(dmitry, yyy_currency, tnb_currency, quantity=2, price=3)

    match = create_match(create_challenge(bucky, dmitry, tnb_currency))
    ConnectFiveMatchPlayer.objects.create(match=match, user=bucky)
    ConnectFiveMatchPlayer.objects.create(match=match, user=dmitry)
    ConnectFiveChatMessage.objects.create(match=match, sender=dmitry, message='Good luck')
    ConnectFiveStats.objects.create(user=bucky, elo=1510, matches_played=1, wins=1)

    return SimpleNamespace(
        asset_pair=order.asset_pair,
        bucky=bucky,
        challenge=match.challenge,
        comment=comment,
        currency=yyy_currency,
        dmitry=dmitry,
        match=match,
        order=order,
        post=post,
        whitepaper=whitepaper,
    )


PUBLIC_READ_URLS = (
    '/api/asset-pairs',
    '/api/asset-pairs/{asset_pair.id}',
    '/api/connect-five/leaderboard',
    '/api/connect-five/matches',
    '/api/connect-five/matches/{match.id}',
    '/api/connect-five/matches/{match.id}/chat',
    '/api/currencies',
    '/api/currencies/{currency.id}',
    '/api/currency-balances?currency={currency.id}',
    '/api/exchange-orders/book?asset_pair={asset_pair.id}',
    '/api/followers?following={bucky.id}',
    '/api/mint-chart-data?currency={currency.id}',
    '/api/mints?currency={currency.id}',
    '/api/post-likes?post={post.id}',
    '/api/posts',
    '/api/posts/{post.id}',
    '/api/posts/{post.id}/tip-amounts',
    '/api/posts?user={bucky.id}',
    '/api/total-amount-minted?currency={currency.id}',
    '/api/trade-history-items?ordering=-volume_24h',
    '/api/trade-price-chart-data?asset_pair={asset_pair.id}&time_range=1d',
    '/api/trades',
    '/api/user-wallets/{dmitry.id}',
    '/api/user/{bucky.id}/stats',
    '/api/users/{bucky.id}',
    '/api/whitepapers/{whitepaper.id}',
    '/api/whitepapers?currency={currency.id}',
)

PRIVATE_READ_URLS = (
    '/api/comments',
    '/api/comments/{comment.id}',
    '/api/connect-five/challenges',
    '/api/connect-five/challenges/{challenge.id}',
    '/api/connect-five/elo-snapshots',
    '/api/connect-five/matches/{match.id}/rematch-status',
    '/api/exchange-orders',
    '/api/exchange-orders/{order.id}',
    '/api/invitation-limits/{bucky.id}',
    '/api/invitations',
    '/api/notifications',
    '/api/notifications/unread-count',
    '/api/transfers?currency={currency.id}',
    '/api/users/search?q=buc',
    '/api/wallets',
    '/api/wallets/default',
    '/api/wires',
)

WRITE_REQUESTS = (
    ('delete', '/api/comments/{comment.id}'),
    ('delete', '/api/currencies/{currency.id}'),
    ('delete', '/api/followers/{bucky.id}'),
    ('delete', '/api/posts/{post.id}'),
    ('delete', '/api/whitepapers/{whitepaper.id}'),
    ('patch', '/api/comments/{comment.id}'),
    ('patch', '/api/currencies/{currency.id}'),
    ('patch', '/api/exchange-orders/{order.id}'),
    ('patch', '/api/notifications/mark-all-as-read'),
    ('patch', '/api/posts/{post.id}'),
    ('patch', '/api/whitepapers/{whitepaper.id}'),
    ('post', '/api/comments'),
    ('post', '/api/connect-five/challenges'),
    ('post', '/api/connect-five/challenges/{challenge.id}/accept'),
    ('post', '/api/connect-five/matches/{match.id}/chat'),
    ('post', '/api/connect-five/matches/{match.id}/move'),
    ('post', '/api/connect-five/matches/{match.id}/purchase'),
    ('post', '/api/connect-five/matches/{match.id}/rematch'),
    ('post', '/api/connect-five/matches/{match.id}/resign'),
    ('post', '/api/currencies'),
    ('post', '/api/exchange-orders'),
    ('post', '/api/followers'),
    ('post', '/api/invitations'),
    ('post', '/api/mints'),
    ('post', '/api/posts'),
    ('post', '/api/posts/{post.id}/like'),
    ('post', '/api/posts/{post.id}/unlike'),
    ('post', '/api/wallets'),
    ('post', '/api/whitepapers'),
)


@pytest.mark.django_db
@pytest.mark.parametrize('url', PUBLIC_READ_URLS)
def test_anonymous_user_can_read_public_content(api_client, content, url):
    response = api_client.get(url.format(**vars(content)))

    assert response.status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize('url', PUBLIC_READ_URLS)
def test_authenticated_user_can_read_public_content(authenticated_api_client, content, url):
    response = authenticated_api_client.get(url.format(**vars(content)))

    assert response.status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize('url', PRIVATE_READ_URLS)
def test_anonymous_user_cannot_read_private_content(api_client, content, url):
    response = api_client.get(url.format(**vars(content)))

    assert response.status_code == 401


@pytest.mark.django_db
@pytest.mark.parametrize(('method', 'url'), WRITE_REQUESTS)
def test_anonymous_user_cannot_write(api_client, content, method, url):
    response = getattr(api_client, method)(url.format(**vars(content)), {}, format='json')

    assert response.status_code == 401


@pytest.mark.django_db
def test_request_with_invalid_token_is_rejected_on_public_endpoints(api_client, content):
    # The frontend relies on this to detect an expired session instead of silently browsing as a guest
    api_client.credentials(HTTP_AUTHORIZATION='Bearer invalid')

    response = api_client.get('/api/posts')

    assert response.status_code == 401


@pytest.mark.django_db
def test_anonymous_user_reads_posts_with_comments_and_without_like_status(api_client, content):
    response = api_client.get('/api/posts')

    assert response.status_code == 200
    assert response.data['count'] == 1
    post = response.data['results'][0]
    assert post['id'] == content.post.id
    assert post['is_liked'] is False
    assert post['like_count'] == 1
    assert [comment['id'] for comment in post['comments']] == [content.comment.id]


@pytest.mark.django_db
def test_like_status_is_still_reported_to_authenticated_user(api_client, content):
    api_client.force_authenticate(content.dmitry)

    response = api_client.get(f'/api/posts/{content.post.id}')

    assert response.status_code == 200
    assert response.data['is_liked'] is True


@pytest.mark.django_db
def test_anonymous_user_reads_followers_without_follow_status(api_client, content):
    response = api_client.get(f'/api/followers?following={content.bucky.id}')

    assert response.status_code == 200
    assert response.data['count'] == 1
    follower = response.data['results'][0]
    assert follower['follower']['id'] == content.dmitry.id
    assert follower['self_following'] is False


@pytest.mark.django_db
def test_anonymous_user_reads_order_book(api_client, content):
    response = api_client.get(f'/api/exchange-orders/book?asset_pair={content.asset_pair.id}')

    assert response.status_code == 200
    assert response.data['sell_orders'] == []
    assert [order['id'] for order in response.data['buy_orders']] == [content.order.id]


@pytest.mark.django_db
def test_anonymous_user_reads_user_wallets_without_deposit_details(api_client, content):
    response = api_client.get(f'/api/user-wallets/{content.dmitry.id}')

    assert response.status_code == 200
    assert {wallet['currency']['ticker']: wallet['balance'] for wallet in response.data} == {'TNB': 994, 'YYY': 250}
    for wallet in response.data:
        assert 'deposit_account_number' not in wallet
        assert 'deposit_signing_key' not in wallet


@pytest.mark.django_db
@pytest.mark.parametrize(
    ('mine', 'expected_count'),
    (
        (None, 1),
        ('exclude', 1),
        ('true', 0),
    ),
)
def test_anonymous_user_filters_matches(api_client, content, mine, expected_count):
    params = {} if mine is None else {'mine': mine}

    response = api_client.get('/api/connect-five/matches', params)

    assert response.status_code == 200
    assert response.data['count'] == expected_count


@pytest.mark.django_db
@pytest.mark.parametrize(
    ('mine', 'expected_count'),
    (
        (None, 1),
        ('exclude', 0),
        ('true', 1),
    ),
)
def test_match_filters_are_unchanged_for_players(authenticated_api_client, content, mine, expected_count):
    params = {} if mine is None else {'mine': mine}

    response = authenticated_api_client.get('/api/connect-five/matches', params)

    assert response.status_code == 200
    assert response.data['count'] == expected_count


@pytest.mark.django_db
def test_anonymous_user_reads_match_chat(api_client, content):
    response = api_client.get(f'/api/connect-five/matches/{content.match.id}/chat')

    assert response.status_code == 200
    assert [message['message'] for message in response.data['results']] == ['Good luck']


@pytest.mark.django_db
def test_page_size_is_capped_for_anonymous_user(api_client, bucky):
    baker.make('social.Post', owner=bucky, image='', _quantity=ANONYMOUS_MAX_PAGE_SIZE + 5)

    response = api_client.get('/api/posts?page_size=10000')

    assert response.status_code == 200
    assert response.data['count'] == ANONYMOUS_MAX_PAGE_SIZE + 5
    assert len(response.data['results']) == ANONYMOUS_MAX_PAGE_SIZE
    assert response.data['next'] is not None


@pytest.mark.django_db
def test_page_size_is_not_capped_for_authenticated_user(authenticated_api_client, bucky):
    baker.make('social.Post', owner=bucky, image='', _quantity=ANONYMOUS_MAX_PAGE_SIZE + 5)

    response = authenticated_api_client.get('/api/posts?page_size=10000')

    assert response.status_code == 200
    assert len(response.data['results']) == ANONYMOUS_MAX_PAGE_SIZE + 5
    assert response.data['next'] is None


@pytest.mark.django_db
def test_default_page_size_is_unchanged_for_anonymous_user(api_client, bucky):
    baker.make('social.Post', owner=bucky, image='', _quantity=25)

    response = api_client.get('/api/posts')

    assert response.status_code == 200
    assert len(response.data['results']) == 20
