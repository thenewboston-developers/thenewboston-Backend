import pytest
from model_bakery import baker


@pytest.mark.django_db
def test_read_cores_as_bucky(api_client_bucky):
    url = '/api/cores'
    response = api_client_bucky.get(url)
    assert response.status_code == 200
    assert response.json() == []

    cores = baker.make('cores.Core', logo=None, _quantity=3)
    expected_cores = [{
        'id': core.id,
        'created_date': core.created_date.replace(tzinfo=None).isoformat() + 'Z',
        'modified_date': core.modified_date.replace(tzinfo=None).isoformat() + 'Z',
        'domain': core.domain,
        'logo': None,
        'ticker': core.ticker,
        'owner': core.owner.id,
    } for core in cores]
    response = api_client_bucky.get(url)
    assert response.status_code == 200
    assert response.json() == sorted(expected_cores, key=lambda x: x['id'])
