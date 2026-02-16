from unittest.mock import patch

import pytest
from model_bakery import baker
from rest_framework import status

from thenewboston.general.enums import MessageType


@pytest.mark.django_db
class TestCommentViewSet:
    def test_create_streams_comment_event(self, authenticated_api_client):
        post = baker.make('social.Post')

        with (
            patch('thenewboston.social.views.comment.CommentConsumer.stream_comment') as stream_comment_mock,
            patch('thenewboston.social.views.comment.transaction.on_commit', side_effect=lambda callback: callback()),
        ):
            response = authenticated_api_client.post('/api/comments', {'content': 'Hello world', 'post': post.id})

        assert response.status_code == status.HTTP_201_CREATED
        assert stream_comment_mock.call_count == 1
        assert stream_comment_mock.call_args.kwargs['message_type'] == MessageType.CREATE_COMMENT
        assert stream_comment_mock.call_args.kwargs['post_id'] == post.id
        assert stream_comment_mock.call_args.kwargs['comment_data']['id'] == response.data['id']

    def test_update_streams_comment_event(self, authenticated_api_client):
        comment = baker.make('social.Comment', owner=authenticated_api_client.forced_user)

        with (
            patch('thenewboston.social.views.comment.CommentConsumer.stream_comment') as stream_comment_mock,
            patch('thenewboston.social.views.comment.transaction.on_commit', side_effect=lambda callback: callback()),
        ):
            response = authenticated_api_client.patch(f'/api/comments/{comment.id}', {'content': 'Updated'})

        assert response.status_code == status.HTTP_200_OK
        assert stream_comment_mock.call_count == 1
        assert stream_comment_mock.call_args.kwargs['message_type'] == MessageType.UPDATE_COMMENT
        assert stream_comment_mock.call_args.kwargs['post_id'] == comment.post_id
        assert stream_comment_mock.call_args.kwargs['comment_data']['id'] == comment.id

    def test_delete_streams_comment_event(self, authenticated_api_client):
        comment = baker.make('social.Comment', owner=authenticated_api_client.forced_user)

        with (
            patch(
                'thenewboston.social.views.comment.CommentConsumer.stream_comment_delete'
            ) as stream_comment_delete_mock,
            patch('thenewboston.social.views.comment.transaction.on_commit', side_effect=lambda callback: callback()),
        ):
            response = authenticated_api_client.delete(f'/api/comments/{comment.id}')

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert stream_comment_delete_mock.call_count == 1
        assert stream_comment_delete_mock.call_args.kwargs['comment_id'] == comment.id
        assert stream_comment_delete_mock.call_args.kwargs['message_type'] == MessageType.DELETE_COMMENT
        assert stream_comment_delete_mock.call_args.kwargs['post_id'] == comment.post_id
