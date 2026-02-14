import pytest
from model_bakery import baker


@pytest.mark.django_db
def test_read_wallets_as_bucky(api_client_bucky):
    url = '/api/wallets'
    response = api_client_bucky.get(url)
    assert response.status_code == 200
    assert response.json() == {'count': 0, 'next': None, 'previous': None, 'results': []}


@pytest.mark.django_db
def test_read_wallets_are_ordered_by_currency_ticker_then_id(api_client_bucky, bucky):
    aaa_currency = baker.make('currencies.Currency', domain='aaa.example', owner=bucky, ticker='AAA')
    mmm_currency = baker.make('currencies.Currency', domain='mmm.example', owner=bucky, ticker='MMM')
    zzz_currency = baker.make('currencies.Currency', domain='zzz.example', owner=bucky, ticker='ZZZ')
    aaa_wallet = baker.make('wallets.Wallet', balance=333, currency=aaa_currency, owner=bucky)
    mmm_wallet = baker.make('wallets.Wallet', balance=111, currency=mmm_currency, owner=bucky)
    zzz_wallet = baker.make('wallets.Wallet', balance=222, currency=zzz_currency, owner=bucky)

    response = api_client_bucky.get('/api/wallets')
    assert response.status_code == 200
    data = response.json()
    result_ids = [wallet['id'] for wallet in data['results']]

    assert data['count'] == 3
    assert result_ids == [aaa_wallet.id, mmm_wallet.id, zzz_wallet.id]


@pytest.mark.django_db
def test_read_wallets_search_filter_by_ticker_and_domain(api_client_bucky, bucky):
    alpha_currency = baker.make('currencies.Currency', domain='alpha.example', owner=bucky, ticker='ALPHA')
    beta_currency = baker.make('currencies.Currency', domain='beta.example', owner=bucky, ticker='BETA')
    baker.make('wallets.Wallet', balance=100, currency=alpha_currency, owner=bucky)
    baker.make('wallets.Wallet', balance=200, currency=beta_currency, owner=bucky)

    ticker_response = api_client_bucky.get('/api/wallets?search=alp')
    assert ticker_response.status_code == 200
    ticker_data = ticker_response.json()
    assert ticker_data['count'] == 1
    assert ticker_data['results'][0]['currency']['ticker'] == 'ALPHA'

    domain_response = api_client_bucky.get('/api/wallets?search=beta.ex')
    assert domain_response.status_code == 200
    domain_data = domain_response.json()
    assert domain_data['count'] == 1
    assert domain_data['results'][0]['currency']['ticker'] == 'BETA'


@pytest.mark.django_db
def test_read_wallets_search_whitespace_returns_unfiltered_results(api_client_bucky, bucky):
    baker.make(
        'wallets.Wallet', currency__domain='moon.example', currency__owner=bucky, currency__ticker='MOON', owner=bucky
    )
    baker.make(
        'wallets.Wallet', currency__domain='star.example', currency__owner=bucky, currency__ticker='STAR', owner=bucky
    )

    response = api_client_bucky.get('/api/wallets?search=   ')
    assert response.status_code == 200
    data = response.json()
    assert data['count'] == 2
    assert len(data['results']) == 2


@pytest.mark.django_db
def test_read_wallets_pagination_respects_page_size(api_client_bucky, bucky):
    for index in range(15):
        baker.make(
            'wallets.Wallet',
            balance=index,
            currency__domain=f'currency-{index}.example',
            currency__owner=bucky,
            currency__ticker=f'C{index:04d}',
            owner=bucky,
        )

    response_page_1 = api_client_bucky.get('/api/wallets?page_size=12&page=1')
    response_page_2 = api_client_bucky.get('/api/wallets?page_size=12&page=2')

    assert response_page_1.status_code == 200
    assert response_page_2.status_code == 200

    page_1_data = response_page_1.json()
    page_2_data = response_page_2.json()

    assert page_1_data['count'] == 15
    assert len(page_1_data['results']) == 12
    assert len(page_2_data['results']) == 3
