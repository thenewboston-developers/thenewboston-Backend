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
        'domain': currency.domain,
        'logo': None,
        'ticker': currency.ticker,
        'owner': {
            'id': currency.owner.id,
            'username': currency.owner.username,
            'avatar': None,
            'is_staff': currency.owner.is_staff,
        },
    } for currency in currencies]
    response = api_client_bucky.get(url)
    assert response.status_code == 200
    assert response.json() == sorted(expected_currencies, key=lambda x: x['id'])
