from thenewboston.product_analytics import client


def test_client_never_polls_for_feature_flags(settings):
    settings.POSTHOG_API_KEY = 'phc_test'
    settings.POSTHOG_ENABLED = True
    settings.POSTHOG_HOST = 'https://posthog.example.com'
    previous = client._client
    try:
        client.initialize_client()
        posthog = client.get_client()
        # The SDK restarts its flag poller in every forked process (Celery's workers) unless local evaluation is off
        posthog._reinit_after_fork()
        assert posthog.enable_local_evaluation is False
        assert posthog.poller is None
    finally:
        client._client = previous
