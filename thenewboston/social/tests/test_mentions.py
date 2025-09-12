import pytest
from django.contrib.auth import get_user_model
from model_bakery import baker

from thenewboston.general.utils.mentions import (
    create_mention_notifications,
    extract_mentions,
    get_mentioned_users,
    replace_mentions_with_links,
    validate_mentions,
)
from thenewboston.notifications.models import Notification
from thenewboston.social.models import Comment, Post

User = get_user_model()


@pytest.mark.django_db
class TestMentionExtraction:
    """Test mention extraction utilities."""

    def test_extract_single_mention(self):
        """Test extracting a single mention from text."""
        text = 'Hello @john_doe how are you?'
        mentions = extract_mentions(text)
        assert mentions == {'john_doe'}

    def test_extract_multiple_mentions(self):
        """Test extracting multiple mentions from text."""
        text = '@alice @bob and @charlie are mentioned'
        mentions = extract_mentions(text)
        assert mentions == {'alice', 'bob', 'charlie'}

    def test_extract_mentions_with_punctuation(self):
        """Test mentions followed by punctuation."""
        text = 'Hey @user1, @user2! and @user3.'
        mentions = extract_mentions(text)
        assert mentions == {'user1', 'user2', 'user3'}

    def test_extract_mentions_multiline(self):
        """Test mentions across multiple lines."""
        text = """First line @user1
        Second line @user2
        Third @user3"""
        mentions = extract_mentions(text)
        assert mentions == {'user1', 'user2', 'user3'}

    def test_no_mentions(self):
        """Test text with no mentions."""
        text = 'This text has no mentions'
        mentions = extract_mentions(text)
        assert mentions == set()

    def test_extract_mentions_empty_text(self):
        """Test extract_mentions with empty text."""
        assert extract_mentions('') == set()
        assert extract_mentions(None) == set()

    def test_extract_mentions_whitespace_only(self):
        """Test extract_mentions with whitespace only."""
        assert extract_mentions('   ') == set()
        assert extract_mentions('\n\t  ') == set()

    def test_invalid_mention_patterns(self):
        """Test that invalid patterns are not extracted."""
        text = 'email@domain.com not@start middle@not'
        mentions = extract_mentions(text)
        assert mentions == set()

    def test_duplicate_mentions(self):
        """Test that duplicates are removed."""
        text = '@user @user @user'
        mentions = extract_mentions(text)
        assert mentions == {'user'}


@pytest.mark.django_db
class TestMentionValidation:
    """Test mention validation against database."""

    def test_validate_existing_users(self):
        """Test validation of existing users."""
        user1 = baker.make(User, username='alice')
        user2 = baker.make(User, username='bob')

        users = validate_mentions({'alice', 'bob', 'nonexistent'})
        assert len(users) == 2
        assert user1 in users
        assert user2 in users

    def test_validate_case_insensitive(self):
        """Test case-insensitive username validation."""
        user = baker.make(User, username='JohnDoe')

        users = validate_mentions({'johndoe', 'JOHNDOE', 'JohnDoe'})
        assert len(users) == 1
        assert users[0] == user

    def test_validate_empty_set(self):
        """Test validation with empty set."""
        users = validate_mentions(set())
        assert users == []

    def test_get_mentioned_users_integration(self):
        """Test full integration of mention extraction and validation."""
        user1 = baker.make(User, username='alice')
        user2 = baker.make(User, username='bob')

        text = 'Hello @alice and @bob and @nonexistent'
        users = get_mentioned_users(text)

        assert len(users) == 2
        assert user1 in users
        assert user2 in users


@pytest.mark.django_db
class TestMentionLinks:
    """Test mention link replacement."""

    def test_replace_mentions_with_links(self):
        """Test replacing mentions with HTML links."""
        baker.make(User, username='alice', id=123)

        text = 'Hello @alice!'
        result = replace_mentions_with_links(text)
        expected = 'Hello <a href="/users/123">@alice</a>!'
        assert result == expected

    def test_replace_multiple_mentions(self):
        """Test replacing multiple mentions."""
        baker.make(User, username='alice', id=1)
        baker.make(User, username='bob', id=2)

        text = '@alice and @bob are here'
        result = replace_mentions_with_links(text)
        assert '<a href="/users/1">@alice</a>' in result
        assert '<a href="/users/2">@bob</a>' in result

    def test_preserve_nonexistent_mentions(self):
        """Test that non-existent users are preserved as-is."""
        baker.make(User, username='alice', id=1)

        text = '@alice and @nonexistent'
        result = replace_mentions_with_links(text)
        assert '<a href="/users/1">@alice</a>' in result
        assert '@nonexistent' in result
        assert '<a href=' not in result.split('@nonexistent')[0][-20:]

    def test_custom_link_format(self):
        """Test custom link format."""
        baker.make(User, username='alice', id=123)

        text = 'Hello @alice!'
        custom_format = '<span data-user="{user_id}">@{username}</span>'
        result = replace_mentions_with_links(text, link_format=custom_format)
        expected = 'Hello <span data-user="123">@alice</span>!'
        assert result == expected

    def test_replace_mentions_empty_text(self):
        """Test replace_mentions_with_links with empty text."""
        assert replace_mentions_with_links('') == ''
        assert replace_mentions_with_links(None) is None

    def test_replace_mentions_no_mentions_found(self):
        """Test replace_mentions_with_links with text that has no mentions."""
        text = 'This text has no mentions at all'
        result = replace_mentions_with_links(text)
        assert result == text  # Should return original text unchanged


@pytest.mark.django_db
class TestMentionNotifications:
    """Test mention notification creation."""

    def test_create_post_mention_notification(self):
        """Test creating notifications for post mentions."""
        mentioner = baker.make(User, username='author')
        mentioned1 = baker.make(User, username='user1')
        mentioned2 = baker.make(User, username='user2')

        create_mention_notifications(
            mentioned_users=[mentioned1, mentioned2], mentioner=mentioner, content_type='post', content_id=123
        )

        notifications = Notification.objects.all()
        assert notifications.count() == 2

        notif1 = notifications.filter(owner=mentioned1).first()
        assert notif1.payload['type'] == 'mention'
        assert notif1.payload['content_type'] == 'post'
        assert notif1.payload['content_id'] == 123
        assert notif1.payload['mentioner_id'] == mentioner.id
        assert notif1.payload['mentioner_username'] == 'author'

    def test_no_self_mention_notification(self):
        """Test that users don't get notified of their own mentions."""
        user = baker.make(User, username='user')

        create_mention_notifications(mentioned_users=[user], mentioner=user, content_type='post', content_id=123)

        assert Notification.objects.count() == 0

    def test_comment_mention_notification(self):
        """Test creating notifications for comment mentions."""
        mentioner = baker.make(User, username='commenter')
        mentioned = baker.make(User, username='mentioned')

        create_mention_notifications(
            mentioned_users=[mentioned], mentioner=mentioner, content_type='comment', content_id=456
        )

        notification = Notification.objects.first()
        assert notification.owner == mentioned
        assert notification.payload['content_type'] == 'comment'
        assert notification.payload['content_id'] == 456


@pytest.mark.django_db
class TestPostMentions:
    """Test mention functionality in posts."""

    def test_post_mention_extraction_on_create(self):
        """Test that mentions are extracted when a post is created."""
        author = baker.make(User, username='author')
        mentioned1 = baker.make(User, username='alice')
        mentioned2 = baker.make(User, username='bob')

        post = Post.objects.create(owner=author, content='Hello @alice and @bob!')

        # Check that mentioned users are saved
        mentioned_users = post.mentioned_users.all()
        assert mentioned_users.count() == 2
        assert mentioned1 in mentioned_users
        assert mentioned2 in mentioned_users

    def test_post_mention_notifications(self):
        """Test that notifications are created for post mentions."""
        author = baker.make(User, username='author')
        mentioned = baker.make(User, username='mentioned')

        # Clear any existing notifications
        Notification.objects.all().delete()

        post = Post.objects.create(owner=author, content='Hey @mentioned check this out!')

        # Check notification was created
        notification = Notification.objects.filter(owner=mentioned).first()
        assert notification is not None
        assert notification.payload['type'] == 'mention'
        assert notification.payload['content_id'] == post.id


@pytest.mark.django_db
class TestCommentMentions:
    """Test mention functionality in comments."""

    def test_comment_mention_extraction_on_create(self):
        """Test that mentions are extracted when a comment is created."""
        post_author = baker.make(User, username='post_author')
        commenter = baker.make(User, username='commenter')
        mentioned = baker.make(User, username='mentioned')

        post = baker.make(Post, owner=post_author)

        comment = Comment.objects.create(owner=commenter, post=post, content='Great post @mentioned!')

        # Check that mentioned users are saved
        mentioned_users = comment.mentioned_users.all()
        assert mentioned_users.count() == 1
        assert mentioned in mentioned_users

    def test_comment_mention_notifications(self):
        """Test that notifications are created for comment mentions."""
        post_author = baker.make(User, username='post_author')
        commenter = baker.make(User, username='commenter')
        mentioned = baker.make(User, username='mentioned')

        post = baker.make(Post, owner=post_author)

        # Clear any existing notifications
        Notification.objects.all().delete()

        comment = Comment.objects.create(owner=commenter, post=post, content='@mentioned what do you think?')

        # Check notification was created
        notification = Notification.objects.filter(owner=mentioned).first()
        assert notification is not None
        assert notification.payload['type'] == 'mention'
        assert notification.payload['content_type'] == 'comment'
        assert notification.payload['content_id'] == comment.id
