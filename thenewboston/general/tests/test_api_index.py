from django.test import Client


def test_api_index_rejects_post_without_csrf_failure():
    # Scanners POST to the root page all day. The answer must be "method not allowed", not a CSRF failure,
    # because CSRF failures are reported to Sentry.
    client = Client(enforce_csrf_checks=True)

    assert client.get('/', secure=True).status_code == 200
    assert client.post('/', secure=True).status_code == 405
