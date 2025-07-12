import pytest
from model_bakery import baker


@pytest.mark.django_db
def test_read_currencies_as_bucky(api_client_bucky):
    url = '/api/currencies'
    response = api_client_bucky.get(url)
    assert response.status_code == 200
    assert response.json() == []

    currencies = baker.make('currencies.Currency', logo=None, _quantity=3)
    expected_currencies = [{
        'id': currency.id,
        'created_date': currency.created_date.replace(tzinfo=None).isoformat() + 'Z',
        'modified_date': currency.modified_date.replace(tzinfo=None).isoformat() + 'Z',
        'description': currency.description,
        'discord_username': currency.discord_username,
        'domain': currency.domain,
        'facebook_username': currency.facebook_username,
        'github_username': currency.github_username,
        'instagram_username': currency.instagram_username,
        'linkedin_username': currency.linkedin_username,
        'logo': None,
        'pinterest_username': currency.pinterest_username,
        'reddit_username': currency.reddit_username,
        'ticker': currency.ticker,
        'tiktok_username': currency.tiktok_username,
        'twitch_username': currency.twitch_username,
        'x_username': currency.x_username,
        'youtube_username': currency.youtube_username,
        'owner': {
            'avatar': None,
            'banner': None,
            'bio': '',
            'discord_username': currency.owner.discord_username,
            'facebook_username': currency.owner.facebook_username,
            'github_username': currency.owner.github_username,
            'id': currency.owner.id,
            'instagram_username': currency.owner.instagram_username,
            'is_staff': currency.owner.is_staff,
            'linkedin_username': currency.owner.linkedin_username,
            'pinterest_username': currency.owner.pinterest_username,
            'reddit_username': currency.owner.reddit_username,
            'tiktok_username': currency.owner.tiktok_username,
            'twitch_username': currency.owner.twitch_username,
            'username': currency.owner.username,
            'x_username': currency.owner.x_username,
            'youtube_username': currency.owner.youtube_username,
        },
    } for currency in currencies]
    response = api_client_bucky.get(url)
    assert response.status_code == 200
    assert response.json() == sorted(expected_currencies, key=lambda x: x['created_date'], reverse=True)
