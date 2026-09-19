import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from model_bakery import baker

from thenewboston.connect_five.models import ConnectFiveStats
from thenewboston.currencies.models import Currency
from thenewboston.social.models import Comment, Post, PostLike
from thenewboston.social.serializers.post import PostReadSerializer

User = get_user_model()


@pytest.fixture
def make_social_post(authenticated_api_client):
    def create():
        owner, recipient, commenter, mentioned_user, currency_owner = baker.make(User, _quantity=5)
        for user, elo in ((owner, 1234), (commenter, 1300), (mentioned_user, 1500), (currency_owner, 1400)):
            baker.make(ConnectFiveStats, user=user, elo=elo)
        currency = baker.make(Currency, owner=currency_owner, logo='')
        post = baker.make(Post, owner=owner, recipient=recipient, price_currency=currency, price_amount=17, image='')
        post.mentioned_users.add(mentioned_user)
        for amount in (3, 7, None):
            comment = baker.make(
                Comment,
                post=post,
                owner=commenter,
                price_amount=amount,
                price_currency=currency if amount is not None else None,
            )
            comment.mentioned_users.add(mentioned_user)
        baker.make(PostLike, post=post, user=authenticated_api_client.forced_user)
        baker.make(PostLike, post=post, user=owner)
        return post

    return create


def get_with_query_count(client, url):
    with CaptureQueriesContext(connection) as queries:
        response = client.get(url)
    assert response.status_code == 200
    return response, len(queries)


@pytest.mark.django_db
class TestSocialReadPerformance:
    def test_post_queries_do_not_grow_with_page_size(self, authenticated_api_client, make_social_post):
        make_social_post()
        _, single_count = get_with_query_count(authenticated_api_client, '/api/posts?page_size=20')
        for _ in range(7):
            make_social_post()

        response, page_count = get_with_query_count(authenticated_api_client, '/api/posts?page_size=20')

        assert len(response.data['results']) == 8
        assert page_count == single_count
        assert page_count <= 10

    def test_post_details_preserve_nested_users_likes_and_tip_totals(self, authenticated_api_client, make_social_post):
        post = make_social_post()
        response, query_count = get_with_query_count(authenticated_api_client, f'/api/posts/{post.id}')
        data = response.data

        assert query_count <= 10
        assert data['owner']['connect_five_elo'] == 1234
        assert data['recipient']['connect_five_elo'] is None
        assert data['mentioned_users'][0]['connect_five_elo'] == 1500
        assert len(data['comments']) == 3
        for comment in data['comments']:
            assert comment['owner']['connect_five_elo'] == 1300
            assert comment['mentioned_users'][0]['connect_five_elo'] == 1500
        assert data['like_count'] == 2
        assert data['is_liked'] is True
        assert len(data['tip_amounts']) == 1
        assert data['tip_amounts'][0]['total_amount'] == 10
        assert data['tip_amounts'][0]['currency']['id'] == post.price_currency_id
        assert data['tip_amounts'][0]['currency']['owner']['connect_five_elo'] == 1400

        other_user = baker.make(User)
        authenticated_api_client.force_authenticate(other_user)
        response = authenticated_api_client.get(f'/api/posts/{post.id}')
        assert response.data['is_liked'] is False
        assert response.data['like_count'] == 2

    def test_tip_amount_action_matches_uncached_serializer(self, authenticated_api_client, make_social_post):
        post = make_social_post()
        extra_currency, zero_currency = baker.make(Currency, owner=post.owner, logo='', _quantity=2)
        for amount, currency in ((13, extra_currency), (0, zero_currency), (100, None), (None, extra_currency)):
            baker.make(Comment, post=post, owner=post.owner, price_amount=amount, price_currency=currency)
        expected = PostReadSerializer().get_tip_amounts(Post.objects.get(pk=post.pk))
        response, query_count = get_with_query_count(authenticated_api_client, f'/api/posts/{post.id}/tip-amounts')

        assert query_count <= 10
        actual_by_currency = {tip['currency']['id']: tip for tip in response.data['tip_amounts']}
        assert actual_by_currency == {tip['currency']['id']: tip for tip in expected}
        assert {currency_id: tip['total_amount'] for currency_id, tip in actual_by_currency.items()} == {
            post.price_currency_id: 10,
            extra_currency.id: 13,
            zero_currency.id: 0,
        }

    def test_comment_queries_do_not_grow_with_result_size(self, authenticated_api_client, make_social_post):
        make_social_post()
        _, single_count = get_with_query_count(authenticated_api_client, '/api/comments?page_size=100')
        for _ in range(7):
            make_social_post()

        response, page_count = get_with_query_count(authenticated_api_client, '/api/comments?page_size=100')

        assert len(response.data['results']) == 24
        assert page_count == single_count
        assert page_count <= 5
        for comment in response.data['results']:
            assert comment['owner']['connect_five_elo'] == 1300
            assert comment['mentioned_users'][0]['connect_five_elo'] == 1500

    def test_comments_without_pagination_keep_list_response(self, authenticated_api_client, make_social_post):
        make_social_post()
        response = authenticated_api_client.get('/api/comments?ordering=-created_date')

        assert response.status_code == 200
        assert isinstance(response.data, list)
        assert len(response.data) == 3

    def test_comments_paginate_when_page_size_is_requested(self, authenticated_api_client, make_social_post):
        post = make_social_post()
        expected_ids = list(post.comments.order_by('-created_date').values_list('id', flat=True))
        first = authenticated_api_client.get('/api/comments?ordering=-created_date&page_size=2')

        assert first.status_code == 200
        assert first.data['count'] == 3
        assert [comment['id'] for comment in first.data['results']] == expected_ids[:2]
        assert first.data['previous'] is None
        second = authenticated_api_client.get(first.data['next'])
        assert second.status_code == 200
        assert [comment['id'] for comment in second.data['results']] == expected_ids[2:]
        assert second.data['next'] is None
        assert second.data['previous'] is not None

    def test_comments_page_size_is_capped(self, authenticated_api_client):
        post = baker.make(Post, owner=authenticated_api_client.forced_user, image='')
        baker.make(Comment, post=post, owner=post.owner, price_amount=None, price_currency=None, _quantity=105)

        response = authenticated_api_client.get('/api/comments?page_size=10000')

        assert response.status_code == 200
        assert response.data['count'] == 105
        assert len(response.data['results']) == 100
        assert response.data['next'] is not None

    def test_comments_page_parameter_uses_default_page_size(self, authenticated_api_client):
        post = baker.make(Post, owner=authenticated_api_client.forced_user, image='')
        baker.make(Comment, post=post, owner=post.owner, price_amount=None, price_currency=None, _quantity=21)

        response = authenticated_api_client.get('/api/comments?page=1')

        assert response.status_code == 200
        assert response.data['count'] == 21
        assert len(response.data['results']) == 20
        assert response.data['next'] is not None
