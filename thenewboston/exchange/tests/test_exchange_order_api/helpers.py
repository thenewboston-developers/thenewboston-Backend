from thenewboston.general.utils.datetime import to_iso_format


def assert_order_response(api_client, response, order, *, status_code=200):
    order.refresh_from_db()
    asset_pair = order.asset_pair

    def currency_data(currency):
        return {
            'id': currency.id,
            'ticker': currency.ticker,
            'logo': response.wsgi_request.build_absolute_uri(currency.logo.url),
        }

    assert response.status_code == status_code
    assert response.json() == {
        'id': order.id,
        'created_date': to_iso_format(order.created_date),
        'modified_date': to_iso_format(order.modified_date),
        'owner': order.owner_id,
        'side': order.side,
        'quantity': order.quantity,
        'price': order.price,
        'filled_quantity': order.filled_quantity,
        'status': order.status,
        'asset_pair': {
            'id': asset_pair.id,
            'primary_currency': currency_data(asset_pair.primary_currency),
            'secondary_currency': currency_data(asset_pair.secondary_currency),
        },
    }
    detail = api_client.get(f'/api/exchange-orders/{order.id}')
    assert (detail.status_code, detail.json()) == (200, response.json())
