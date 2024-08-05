from django.contrib.auth import get_user_model


def get_ia():
    return get_user_model().objects.get(username='ia')
