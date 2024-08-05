from django.test import override_settings

from thenewboston.general.tests.vcr import assert_played, yield_cassette


def test_create_openai_images(api_client_bucky, sample_core, sample_wallet):
    payload = {
        'description': 'A cat',
        'quantity': 1,
    }
    with (
        override_settings(OPENAI_IMAGE_GENERATION_DEFAULT_SIZE='256x256'),
        yield_cassette('create_openai_image.yaml') as cassette,
        assert_played(cassette),
    ):
        response = api_client_bucky.post('/api/openai_images', payload)

    assert response.status_code == 200
    assert response.json() == {
        'created':
            1722953410,
        'data': [{
            'b64_json':
                None,
            'revised_prompt':
                None,
            'url': (
                'https://oaidalleapiprodscus.blob.core.windows.net/private/'
                'org-eQnfyttwsLTbvwJtDWRGilzo/user-vGa8V5qOL8XFkzK6S4wA3Geo/'
                'img-bY1bAO8t1NOd3M9w3HE6TSW6.png?st=2024-08-06T13%3A10%3A10Z&'
                'se=2024-08-06T15%3A10%3A10Z&sp=r&sv=2023-11-03&sr=b&rscd=inline&'
                'rsct=image/png&skoid=d505667d-d6c1-4a0a-bac7-5c84a87759f8&'
                'sktid=a48cca56-e6da-484e-a814-9c849652bcb3&skt=2024-08-06T01%3A30%3A12Z&'
                'ske=2024-08-07T01%3A30%3A12Z&sks=b&skv=2023-11-03&sig=9BK9xQF5a6CWqDV6QVNy4Ktmh19jrYOOlWiZys6qVrM%3D'
            )
        }]
    }
