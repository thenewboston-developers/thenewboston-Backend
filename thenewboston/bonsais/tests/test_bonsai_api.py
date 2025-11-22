import json
from decimal import Decimal
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from model_bakery import baker
from PIL import Image

from thenewboston.bonsais.models import Bonsai


def create_test_image_file(name='test.jpg', color=(255, 0, 0)):
    buffer = BytesIO()
    image = Image.new('RGB', (10, 10), color)
    image.save(buffer, format='JPEG')
    buffer.seek(0)
    return SimpleUploadedFile(name, buffer.read(), content_type='image/jpeg')


@pytest.fixture
def temp_media_root(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


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
    assert response.data['count'] == 1
    assert len(response.data['results']) == 1
    assert response.data['results'][0]['slug'] == 'published-bonsai'


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
    assert response.data['count'] == 2
    assert {bonsai['slug'] for bonsai in response.data['results']} == {'published-bonsai', 'draft-bonsai'}


@pytest.mark.django_db
def test_staff_can_create_bonsai(api_client_bucky_staff, tnb_currency, temp_media_root):
    image_one_field = 'image_0'
    image_two_field = 'image_1'
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
        'price_currency_id': str(tnb_currency.id),
        'status': Bonsai.Status.PUBLISHED,
        'highlights': json.dumps(
            [
                {'text': 'First highlight', 'order': 1},
                {'text': 'Second highlight'},
            ]
        ),
        'images': json.dumps(
            [
                {'image_field': image_one_field, 'order': 2},
                {'image_field': image_two_field},
            ]
        ),
    }
    payload[image_one_field] = create_test_image_file('1.jpg')
    payload[image_two_field] = create_test_image_file('2.jpg')

    response = api_client_bucky_staff.post('/api/bonsais', payload, format='multipart')

    assert response.status_code == 201
    bonsai = Bonsai.objects.get(slug='ancient-pine')
    assert bonsai.highlights.count() == 2
    assert bonsai.images.count() == 2
    assert bonsai.status == Bonsai.Status.PUBLISHED


@pytest.mark.django_db
def test_staff_can_update_nested_collections(api_client_bucky_staff, tnb_currency, temp_media_root):
    bonsai = baker.make(
        'bonsais.Bonsai',
        slug='mossy-maple',
        price_currency=tnb_currency,
        price_amount=Decimal('2000.00'),
        status=Bonsai.Status.DRAFT,
    )
    highlight = baker.make('bonsais.BonsaiHighlight', bonsai=bonsai, text='Old highlight', order=0)
    baker.make('bonsais.BonsaiHighlight', bonsai=bonsai, text='To remove', order=1)
    baker.make('bonsais.BonsaiImage', bonsai=bonsai, image=create_test_image_file('old.jpg'), order=0)

    payload = {
        'name': 'Updated Maple',
        'price_currency_id': str(tnb_currency.id),
        'highlights': json.dumps(
            [
                {'id': highlight.id, 'text': 'Updated highlight text', 'order': 0},
                {'text': 'Brand new highlight', 'order': 1},
            ]
        ),
        'images': json.dumps(
            [
                {'image_field': 'image_0', 'order': 0},
            ]
        ),
        'status': Bonsai.Status.PUBLISHED,
    }
    payload['image_0'] = create_test_image_file('new.jpg')

    response = api_client_bucky_staff.patch(f'/api/bonsais/{bonsai.slug}', payload, format='multipart')

    assert response.status_code == 200
    bonsai.refresh_from_db()
    assert bonsai.name == 'Updated Maple'
    assert bonsai.status == Bonsai.Status.PUBLISHED
    assert list(bonsai.highlights.values_list('text', flat=True)) == [
        'Updated highlight text',
        'Brand new highlight',
    ]
    assert bonsai.images.count() == 1
    assert bonsai.images.first().image.name.startswith('bonsai_images/')
