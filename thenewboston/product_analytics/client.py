import logging

from django.conf import settings

logger = logging.getLogger(__name__)
_client = None


def initialize_client():
    global _client
    if not settings.POSTHOG_ENABLED:
        return
    for name in ('POSTHOG_API_KEY', 'POSTHOG_HOST'):
        if not getattr(settings, name, ''):
            if not settings.IS_DEPLOYED:
                logger.warning(
                    '%s variable required by PostHog is missing or un-configured, this causes events to be '
                    'silently missed. This error stops appearing once %s is configured',
                    name,
                    name,
                )
            return
    try:
        from posthog import Posthog

        # Only the outbox worker uses this synchronous client. HTTP requests never send analytics.
        _client = Posthog(
            settings.POSTHOG_API_KEY,
            host=settings.POSTHOG_HOST,
            sync_mode=True,
            timeout=3,
            max_retries=0,
            disable_geoip=True,
            enable_exception_autocapture=False,
        )
    except Exception:
        logger.exception('Could not initialize product analytics')


def get_client():
    return _client
