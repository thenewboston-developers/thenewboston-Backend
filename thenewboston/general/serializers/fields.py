from django.conf import settings
from rest_framework import serializers


class AbsoluteURLImageField(serializers.ImageField):

    def to_representation(self, value):
        if not value:
            return None

        url = value.url
        request = self.context.get('request')

        if request and not url.startswith(('http://', 'https://')):
            return request.build_absolute_uri(url)

        if url.startswith(('http://', 'https://')):
            return url

        base_url = getattr(settings, 'BASE_URL', 'http://localhost:8000')
        return f"{base_url.rstrip('/')}{url}"
