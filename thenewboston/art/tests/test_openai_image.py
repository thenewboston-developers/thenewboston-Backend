from django.test import override_settings

from thenewboston.general.tests.vcr import assert_played, yield_cassette


def test_create_openai_images(api_client_bucky):
    payload = {
        'description': 'A cat',
        'quantity': 1,
    }
    with (
        override_settings(OPENAI_IMAGE_GENERATION_DEFAULT_SIZE='256x256'),
        yield_cassette('create_openai_image.yaml') as cassette,
        assert_played(cassette, count=2),
    ):
        response = api_client_bucky.post('/api/openai_images', payload)

    assert response.status_code == 200
    assert response.json() == {
        'created':
            1712242615,
        'data': [{
            'b64_json':
                None,
            'revised_prompt':
                None,
            'url': (
                'https://oaidalleapiprodscus.blob.core.windows.net/'
                'private/org-eQnfyttwsLTbvwJtDWRGilzo/user-vGa8V5qOL8XFkzK6S4wA3Geo/'
                'img-gPfLBQY2J1mBxhd81nLYuOHz.png?st=2024-04-04T13%3A56%3A55Z&se=2024-04-04T15%3A56%3A55Z&sp=r&'
                'sv=2021-08-06&sr=b&rscd=inline&rsct=image/png&'
                'skoid=6aaadede-4fb3-4698-a8f6-684d7786b067&sktid=a48cca56-e6da-484e-a814-9c849652bcb3&'
                'skt=2024-04-03T20%3A15%3A27Z&ske=2024-04-04T20%3A15%3A27Z&sks=b&skv=2021-08-06&'
                'sig=KtLaFr26odFV%2BeJlINYQN0t5utSfCpRYhpToZqhcWW0%3D'
            )
        }]
    }
