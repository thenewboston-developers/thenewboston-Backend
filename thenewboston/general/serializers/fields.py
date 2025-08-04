from django.conf import settings
from rest_framework import serializers


class AbsoluteURLImageField(serializers.ImageField):
    """
    ImageField that always returns absolute URLs regardless of request context.

    This field ensures consistent URL generation for images whether serialization
    happens in views (with request context) or background tasks (without context).
    """

    def to_representation(self, value):
        if not value:
            return None

        url = value.url
        request = self.context.get('request')

        # Use request context if available and URL is relative
        if request and not url.startswith(('http://', 'https://')):
            return request.build_absolute_uri(url)

        # S3 and other external storage backends already return absolute URLs
        if url.startswith(('http://', 'https://')):
            return url

        # Fallback to configured BASE_URL for local development without request context
        base_url = getattr(settings, 'BASE_URL', 'http://localhost:8000')
        return f"{base_url.rstrip('/')}{url}"
