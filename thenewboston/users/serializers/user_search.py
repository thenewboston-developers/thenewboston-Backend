from django.contrib.auth import get_user_model

from thenewboston.general.serializers import BaseModelSerializer

User = get_user_model()


class UserSearchSerializer(BaseModelSerializer):
    """
    Minimal serializer for user search results.
    Returns only essential fields to optimize performance.
    """

    class Meta:
        model = User
        fields = (
            'id',
            'username',
            'avatar',  # This will serve as profile_pic
        )
