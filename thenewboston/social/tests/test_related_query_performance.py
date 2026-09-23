from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from model_bakery import baker
from rest_framework.test import APIRequestFactory

from thenewboston.connect_five.models import ConnectFiveStats
from thenewboston.notifications.models import Notification
from thenewboston.social.models import Comment, Follower, Post, PostLike
from thenewboston.social.utils.mentions import derive_mentioned_user_ids, notify_mentioned_users_in_comment

User = get_user_model()


def get_with_query_count(client, url):
    with CaptureQueriesContext(connection) as queries:
        response = client.get(url)
    assert response.status_code == 200
    return response.data, len(queries)


@pytest.mark.django_db
class TestRelatedSocialQueryPerformance:
    def test_followers_join_user_stats_and_batch_following_status(self, authenticated_api_client):
        viewer = authenticated_api_client.forced_user
        profile = baker.make(User)
        users = baker.make(User, _quantity=8)
        baker.make(ConnectFiveStats, user=profile, elo=1500)
        for user in users[::2]:
            baker.make(ConnectFiveStats, user=user, elo=1200)
            baker.make(Follower, follower=viewer, following=user)
        baker.make(Follower, follower=users[0], following=profile)
        url = f'/api/followers?following={profile.pk}&page_size=20'
        _, single_count = get_with_query_count(authenticated_api_client, url)
        for user in users[1:]:
            baker.make(Follower, follower=user, following=profile)

        data, page_count = get_with_query_count(authenticated_api_client, url)

        assert page_count == single_count
        assert page_count <= 4
        assert len(data['results']) == 8
        followed_ids = {user.pk for user in users[::2]}
        for row in data['results']:
            expected_following = row['follower']['id'] in followed_ids
            assert row['self_following'] is expected_following
            assert row['follower']['connect_five_elo'] == (1200 if expected_following else None)
            assert row['following']['connect_five_elo'] == 1500

    def test_post_likes_join_user_stats(self, authenticated_api_client):
        post = baker.make(Post, owner=authenticated_api_client.forced_user, image='')
        users = baker.make(User, _quantity=8)
        baker.make(ConnectFiveStats, user=users[0], elo=1400)
        baker.make(PostLike, post=post, user=users[0])
        url = f'/api/post-likes?post={post.pk}&page_size=20'
        _, single_count = get_with_query_count(authenticated_api_client, url)
        for user in users[1:]:
            baker.make(PostLike, post=post, user=user)

        data, page_count = get_with_query_count(authenticated_api_client, url)

        assert page_count == single_count
        assert page_count <= 4
        assert len(data['results']) == 8
        for row in data['results']:
            assert row['user']['connect_five_elo'] == (1400 if row['user']['id'] == users[0].pk else None)

    def test_post_update_queries_do_not_grow_with_comments(self, authenticated_api_client):
        post = baker.make(Post, owner=authenticated_api_client.forced_user, image='')
        users = baker.make(User, _quantity=8)

        def add_comment(user):
            baker.make(ConnectFiveStats, user=user, elo=1400)
            comment = baker.make(Comment, post=post, owner=user, price_amount=None, price_currency=None)
            comment.mentioned_users.add(user)

        def update_post():
            with CaptureQueriesContext(connection) as queries:
                response = authenticated_api_client.patch(
                    f'/api/posts/{post.pk}', {'content': 'Updated post'}, format='multipart'
                )
            assert response.status_code == 200
            return response.data, len(queries)

        add_comment(users[0])
        _, single_count = update_post()
        for user in users[1:]:
            add_comment(user)

        data, page_count = update_post()

        assert page_count == single_count
        assert len(data['comments']) == 8
        assert data['content'] == 'Updated post'
        for comment in data['comments']:
            assert comment['owner']['connect_five_elo'] == 1400
            assert comment['mentioned_users'][0]['connect_five_elo'] == 1400

    def test_mention_lookup_uses_one_case_insensitive_query(self, django_assert_num_queries):
        first = baker.make(User, username='Mentioned')
        baker.make(User, username='mentioned')
        users = [first, *baker.make(User, _quantity=7)]
        content = ' '.join(f'@{user.username.upper()}' for user in users) + ' @MENTIONED @missing'

        with django_assert_num_queries(1):
            ids = derive_mentioned_user_ids(content)

        assert set(ids) == {user.pk for user in users}
        assert len(ids) == len(users)
        with django_assert_num_queries(0):
            assert derive_mentioned_user_ids('No mentions') == []

    @pytest.mark.parametrize('resource', ['posts', 'comments'])
    def test_create_mentions_keeps_reads_constant_and_streams_notifications(
        self, authenticated_api_client, django_capture_on_commit_callbacks, resource
    ):
        users = [baker.make(User, username=f'mention_target_{index}') for index in range(8)]
        for user in users[:-1]:
            baker.make(ConnectFiveStats, user=user, elo=1300)
        post = baker.make(Post, owner=authenticated_api_client.forced_user, image='')

        def create(mentioned_users):
            data = {'content': ' '.join(f'@{user.username}' for user in mentioned_users)}
            if resource == 'comments':
                data['post'] = post.pk
            with patch('thenewboston.social.utils.mentions.NotificationConsumer.stream_notification') as stream:
                with CaptureQueriesContext(connection) as queries:
                    with django_capture_on_commit_callbacks(execute=True):
                        response = authenticated_api_client.post(
                            f'/api/{resource}', data, format='multipart' if resource == 'posts' else 'json'
                        )
            assert response.status_code == 201
            assert stream.call_count == len(mentioned_users)
            select_count = sum(query['sql'].lstrip().upper().startswith('SELECT') for query in queries)
            return response.data, select_count

        _, single_count = create(users[:1])
        Notification.objects.all().delete()
        data, page_count = create(users)

        assert page_count == single_count
        assert len(data['mentioned_users']) == 8
        for user in data['mentioned_users']:
            assert user['connect_five_elo'] == (None if user['id'] == users[-1].pk else 1300)
        assert set(Notification.objects.values_list('owner_id', flat=True)) == {user.pk for user in users}
        for payload in Notification.objects.values_list('payload', flat=True):
            assert payload['notification_type'] == ('POST_MENTION' if resource == 'posts' else 'COMMENT_MENTION')
            assert payload['mentioner']['id'] == authenticated_api_client.forced_user.pk
            if resource == 'comments':
                assert payload['comment'] == data

    def test_comment_notification_payload_is_serialized_once(self, authenticated_api_client):
        author = authenticated_api_client.forced_user
        post = baker.make(Post, owner=author, image='')
        comment = baker.make(Comment, post=post, owner=author, price_amount=None, price_currency=None)
        recipients = baker.make(User, _quantity=8)
        comment.mentioned_users.set(recipients)
        baker.make(ConnectFiveStats, user=recipients[0], elo=1300)
        request = APIRequestFactory().get('/')
        request.user = author

        def notify(recipient_ids):
            instance = Comment.objects.get(pk=comment.pk)
            with patch('thenewboston.social.utils.mentions.NotificationConsumer.stream_notification'):
                with CaptureQueriesContext(connection) as queries:
                    notify_mentioned_users_in_comment(instance, recipient_ids, request)
            return sum(query['sql'].lstrip().upper().startswith('SELECT') for query in queries)

        single_count = notify([recipients[0].pk])
        Notification.objects.all().delete()
        all_count = notify([author.pk, *(user.pk for user in recipients)])

        assert all_count == single_count
        assert Notification.objects.count() == len(recipients)
        payloads = list(Notification.objects.values_list('payload', flat=True))
        assert all(payload == payloads[0] for payload in payloads)
        assert payloads[0]['comment']['id'] == comment.pk
        assert payloads[0]['mentioner']['id'] == author.pk
        mentioned = {user['id']: user for user in payloads[0]['comment']['mentioned_users']}
        assert mentioned[recipients[0].pk]['connect_five_elo'] == 1300
