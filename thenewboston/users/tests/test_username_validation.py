import pytest
from django.core.exceptions import ValidationError

from thenewboston.users.models import User
from thenewboston.users.serializers.user import UserWriteSerializer
from thenewboston.users.validators import username_validator


def test_valid_usernames():
    valid_usernames = [
        'ab',
        'user123',
        'test_user',
        'John_Doe_123',
        'a' * 150,
    ]

    for username in valid_usernames:
        assert username_validator(username) == username


def test_length_constraints():
    with pytest.raises(ValidationError) as exc_info:
        username_validator('a')
    assert 'at least 2 characters' in str(exc_info.value)

    with pytest.raises(ValidationError) as exc_info:
        username_validator('a' * 151)
    assert 'cannot be longer than 150 characters' in str(exc_info.value)


def test_allowed_characters():
    invalid_usernames = [
        'user.name',
        'user@name',
        'user-name',
        'user name',
        'user!name',
    ]

    for username in invalid_usernames:
        with pytest.raises(ValidationError) as exc_info:
            username_validator(username)
        assert 'only contain letters, numbers, and underscores' in str(exc_info.value)


def test_forbidden_patterns():
    with pytest.raises(ValidationError) as exc_info:
        username_validator('_username')
    assert 'cannot start or end with' in str(exc_info.value)

    with pytest.raises(ValidationError) as exc_info:
        username_validator('username_')
    assert 'cannot start or end with' in str(exc_info.value)

    with pytest.raises(ValidationError) as exc_info:
        username_validator('user__name')
    assert 'consecutive underscores' in str(exc_info.value)


def test_reserved_words():
    reserved = [
        'admin',
        'Admin',
        'ADMIN',
        'support',
        'Support',
        'moderator',
        'Moderator',
        'thenewboston',
        'TheNewBoston',
        'ia',
        'IA',
    ]

    for username in reserved:
        with pytest.raises(ValidationError) as exc_info:
            username_validator(username)
        assert 'reserved and cannot be used' in str(exc_info.value)


@pytest.mark.django_db
def test_case_insensitive_uniqueness():
    User.objects.create_user(username='Bucky', password='testpass123')

    serializer = UserWriteSerializer(
        data={'username': 'bucky', 'password': 'ValidPass123!', 'invitation_code': 'test_code'}
    )

    assert not serializer.is_valid()
    assert 'username' in serializer.errors
    assert 'already exists' in str(serializer.errors['username'])

    for username in ['BUCKY', 'BuCkY', 'bUcKy']:
        serializer = UserWriteSerializer(
            data={'username': username, 'password': 'ValidPass123!', 'invitation_code': 'test_code'}
        )
        assert not serializer.is_valid()
        assert 'username' in serializer.errors


@pytest.mark.django_db
def test_original_case_preserved():
    serializer = UserWriteSerializer()

    validated_username = serializer.validate_username('TestUser')
    assert validated_username == 'TestUser'

    validated_username = serializer.validate_username('JohnDoe123')
    assert validated_username == 'JohnDoe123'
