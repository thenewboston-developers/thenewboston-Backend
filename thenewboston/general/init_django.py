import os


def init_django():
    import django

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'thenewboston.project.settings')
    django.setup()
