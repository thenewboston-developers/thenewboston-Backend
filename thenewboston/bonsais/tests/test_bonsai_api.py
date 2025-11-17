from decimal import Decimal

import pytest
from model_bakery import baker

from thenewboston.bonsais.models import Bonsai


@pytest.mark.django_db
def test_public_list_shows_only_published(api_client, tnb_currency):
    baker.make(
        'bonsais.Bonsai',
        slug='published-bonsai',
        status=Bonsai.Status.PUBLISHED,
        price_currency=tnb_currency,
        price_amount=Decimal('100.00'),
    )
    baker.make(
        'bonsais.Bonsai',
        slug='draft-bonsai',
        status=Bonsai.Status.DRAFT,
        price_currency=tnb_currency,
        price_amount=Decimal('200.00'),
    )

    response = api_client.get('/api/bonsais')

    assert response.status_code == 200
    assert len(response.data) == 1
    assert response.data[0]['slug'] == 'published-bonsai'


@pytest.mark.django_db
def test_staff_list_includes_drafts(api_client_bucky_staff, tnb_currency):
    baker.make(
        'bonsais.Bonsai',
        slug='published-bonsai',
        status=Bonsai.Status.PUBLISHED,
        price_currency=tnb_currency,
        price_amount=Decimal('100.00'),
    )
    baker.make(
        'bonsais.Bonsai',
        slug='draft-bonsai',
        status=Bonsai.Status.DRAFT,
        price_currency=tnb_currency,
        price_amount=Decimal('200.00'),
    )

    response = api_client_bucky_staff.get('/api/bonsais')

    assert response.status_code == 200
    assert {bonsai['slug'] for bonsai in response.data} == {'published-bonsai', 'draft-bonsai'}


@pytest.mark.django_db
def test_staff_can_create_bonsai(api_client_bucky_staff, tnb_currency):
    payload = {
        'slug': 'ancient-pine',
        'name': 'Ancient Pine',
        'species': 'Japanese Black Pine',
        'style': 'Informal Upright',
        'size': '28in tall, 24in wide',
        'origin': 'Pacific Northwest',
        'pot': 'Tokoname',
        'teaser': 'A windswept pine.',
        'description': 'Detailed description.',
        'price_amount': '4600.00',
        'price_currency_id': tnb_currency.id,
        'status': Bonsai.Status.PUBLISHED,
        'highlights': [
            {'text': 'First highlight', 'order': 1},
            {'text': 'Second highlight'},
        ],
        'images': [
            {'url': 'https://example.com/1.jpg', 'order': 2},
            {'url': 'https://example.com/2.jpg'},
        ],
    }

    response = api_client_bucky_staff.post('/api/bonsais', payload, format='json')

    assert response.status_code == 201
    bonsai = Bonsai.objects.get(slug='ancient-pine')
    assert bonsai.highlights.count() == 2
    assert bonsai.images.count() == 2
    assert bonsai.status == Bonsai.Status.PUBLISHED


@pytest.mark.django_db
def test_staff_can_update_nested_collections(api_client_bucky_staff, tnb_currency):
    bonsai = baker.make(
        'bonsais.Bonsai',
        slug='mossy-maple',
        price_currency=tnb_currency,
        price_amount=Decimal('2000.00'),
        status=Bonsai.Status.DRAFT,
    )
    highlight = baker.make('bonsais.BonsaiHighlight', bonsai=bonsai, text='Old highlight', order=0)
    baker.make('bonsais.BonsaiHighlight', bonsai=bonsai, text='To remove', order=1)
    baker.make('bonsais.BonsaiImage', bonsai=bonsai, url='https://example.com/old.jpg', order=0)

    payload = {
        'name': 'Updated Maple',
        'price_currency_id': tnb_currency.id,
        'highlights': [
            {'id': highlight.id, 'text': 'Updated highlight text', 'order': 0},
            {'text': 'Brand new highlight', 'order': 1},
        ],
        'images': [
            {'url': 'https://example.com/new.jpg', 'order': 0},
        ],
        'status': Bonsai.Status.PUBLISHED,
    }

    response = api_client_bucky_staff.patch(f'/api/bonsais/{bonsai.slug}', payload, format='json')

    assert response.status_code == 200
    bonsai.refresh_from_db()
    assert bonsai.name == 'Updated Maple'
    assert bonsai.status == Bonsai.Status.PUBLISHED
    assert list(bonsai.highlights.values_list('text', flat=True)) == [
        'Updated highlight text',
        'Brand new highlight',
    ]
    assert bonsai.images.count() == 1
    assert bonsai.images.first().url == 'https://example.com/new.jpg'
