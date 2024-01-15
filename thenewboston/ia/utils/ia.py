from django.contrib.auth import get_user_model

User = get_user_model()


def get_ia():
    return User.objects.get(username='ia')
