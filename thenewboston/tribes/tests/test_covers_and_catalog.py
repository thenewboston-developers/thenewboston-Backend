"""Public rules and administrator-managed, validated tournament artwork."""

from copy import deepcopy
from datetime import timedelta
from io import BytesIO
from uuid import UUID

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from freezegun import freeze_time
from model_bakery import baker
from PIL import Image
from rest_framework.exceptions import PermissionDenied, ValidationError as ActionValidationError

from thenewboston.tribes import services, views
from thenewboston.tribes.images import MAX_COVER_BYTES
from thenewboston.tribes.models import Tournament
from thenewboston.tribes.rules import catalog

from .test_admin import setup_payload
from .test_integrity import client_for

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def cover_storage(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    settings.MEDIA_URL = '/media/'
    return tmp_path


@pytest.fixture
def cover_admin():
    actor = baker.make('users.User', is_staff=True, is_superuser=True)
    client = Client()
    client.force_login(actor)
    return client, actor


@pytest.fixture
def cover_tournament(cover_admin):
    return services.create_tournament(
        title='Cover test', starts_at=timezone.now() + timedelta(days=2), max_players=12, actor=cover_admin[1]
    )


def image_upload(*, size=(2400, 1200), image_format='PNG', color='navy'):
    output = BytesIO()
    Image.new('RGB', size, color).save(output, format=image_format)
    return SimpleUploadedFile(
        f'private-original-name.{image_format.lower()}', output.getvalue(), content_type='image/png'
    )


def test_anonymous_catalog_is_available_without_a_tournament_or_game_mutation(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('The public catalog must not advance game state.')

    monkeypatch.setattr(services, 'advance_tournament', forbidden)
    monkeypatch.setattr(services, 'sweep_tournaments', forbidden)
    monkeypatch.setattr(views, 'sweep_tournaments', forbidden)
    response = client_for().get('/api/tribes/catalog')
    assert response.status_code == 200
    assert response.data == catalog()
    assert not Tournament.objects.exists()
    assert client_for().post('/api/tribes/catalog', {}, format='json').status_code == 405


def test_admin_upload_is_normalized_and_exposed_in_public_summaries(cover_admin):
    client, _ = cover_admin
    start = timezone.now() + timedelta(days=2)
    response = client.post(reverse('admin:tribes_tournament_add'), setup_payload(start, cover_image=image_upload()))
    assert response.status_code == 302
    tournament = Tournament.objects.get()
    assert tournament.cover_image.name.startswith('images/tribes/covers/')
    assert tournament.cover_image.name.endswith('.jpg')
    assert UUID(tournament.cover_image.name.split('/')[-1].removesuffix('.jpg')).version == 4
    with tournament.cover_image.open('rb') as saved, Image.open(saved) as picture:
        assert picture.format == 'JPEG'
        assert picture.size == (1600, 800)
    public = client_for().get('/api/tribes/tournaments').data[0]
    assert public['cover_image'] == f'http://testserver/media/{tournament.cover_image.name}'
    detail = client_for().get('/api/tribes/state', {'tournament_id': tournament.pk}).data
    assert detail['tournament']['cover_image'] == public['cover_image']
    assert detail['tournament']['is_participant'] is False


def test_admin_edit_retains_replaces_and_clears_cover_without_changing_roster(cover_admin, cover_tournament):
    client, actor = cover_admin
    tournament = cover_tournament
    user = baker.make('users.User')
    services.add_participant(tournament.pk, user.pk, actor=actor)
    tournament = services.create_tribe(tournament.pk, name='Pines', founder_id=user.pk, actor=actor)
    original_state = deepcopy(tournament.state)
    url = reverse('admin:tribes_tournament_change', args=[tournament.pk])
    assert client.post(url, setup_payload(tournament.starts_at, cover_image=image_upload())).status_code == 302
    tournament.refresh_from_db()
    first = tournament.cover_image.name
    storage = tournament.cover_image.storage
    assert client.post(url, setup_payload(tournament.starts_at, title='Renamed')).status_code == 302
    tournament.refresh_from_db()
    assert tournament.cover_image.name == first
    assert tournament.title == 'Renamed'
    assert (
        client.post(url, setup_payload(tournament.starts_at, cover_image=image_upload(color='green'))).status_code
        == 302
    )
    tournament.refresh_from_db()
    second = tournament.cover_image.name
    assert second != first
    assert storage.exists(second)
    assert not storage.exists(first)
    assert client.post(url, setup_payload(tournament.starts_at, **{'cover_image-clear': 'on'})).status_code == 302
    tournament.refresh_from_db()
    assert not tournament.cover_image
    assert not storage.exists(second)
    assert tournament.state == original_state
    assert tournament.participants.filter(user=user).exists()
    assert client_for().get('/api/tribes/tournaments').data[0]['cover_image'] is None


@pytest.mark.parametrize('kind', ['invalid', 'unsupported', 'oversized', 'too_many_pixels'])
def test_admin_rejects_invalid_covers_without_saving_a_tournament(cover_admin, cover_storage, kind):
    client, _ = cover_admin
    if kind == 'invalid':
        upload = SimpleUploadedFile('bad.png', b'not a picture', content_type='image/png')
    elif kind == 'unsupported':
        upload = image_upload(size=(10, 10), image_format='GIF')
    elif kind == 'oversized':
        upload = SimpleUploadedFile('large.png', b'x' * (MAX_COVER_BYTES + 1), content_type='image/png')
    else:
        upload = image_upload(size=(5001, 5000))
    response = client.post(
        reverse('admin:tribes_tournament_add'),
        setup_payload(timezone.now() + timedelta(days=2), cover_image=upload),
    )
    assert response.status_code == 200
    assert 'cover_image' in response.context['adminform'].form.errors
    assert not Tournament.objects.exists()
    assert not [path for path in cover_storage.rglob('*') if path.is_file()]


def test_cover_services_enforce_permissions_and_cutoff(cover_admin, cover_tournament, cover_storage):
    _, actor = cover_admin
    tournament = cover_tournament
    values = {'title': tournament.title, 'starts_at': tournament.starts_at, 'max_players': tournament.max_players}
    outsider = baker.make('users.User')
    with pytest.raises(PermissionDenied):
        services.update_tournament(tournament.pk, actor=outsider, cover_image=image_upload(), **values)
    with freeze_time(tournament.starts_at), pytest.raises(ActionValidationError, match='locked'):
        services.update_tournament(tournament.pk, actor=actor, cover_image=image_upload(), **values)
    assert not [path for path in cover_storage.rglob('*') if path.is_file()]
    tournament.refresh_from_db()
    assert not tournament.cover_image
    unauthorized = Client()
    unauthorized.force_login(outsider)
    assert (
        unauthorized.post(
            reverse('admin:tribes_tournament_change', args=[tournament.pk]),
            setup_payload(tournament.starts_at, cover_image=image_upload()),
        ).status_code
        == 302
    )  # Admin redirects non-staff to its login.


def test_invalid_service_upload_and_capacity_do_not_replace_existing_cover(cover_admin, cover_tournament):
    _, actor = cover_admin
    tournament = cover_tournament
    values = {'title': tournament.title, 'starts_at': tournament.starts_at, 'max_players': tournament.max_players}
    tournament = services.update_tournament(tournament.pk, actor=actor, cover_image=image_upload(), **values)
    original = tournament.cover_image.name
    with pytest.raises(ValidationError):
        services.update_tournament(
            tournament.pk, actor=actor, cover_image=SimpleUploadedFile('fake.png', b'broken'), **values
        )
    for _ in range(2):
        services.add_participant(tournament.pk, baker.make('users.User').pk, actor=actor)
    with pytest.raises(ActionValidationError, match='Capacity'):
        services.update_tournament(
            tournament.pk, actor=actor, cover_image=image_upload(), **{**values, 'max_players': 1}
        )
    tournament.refresh_from_db()
    assert tournament.cover_image.name == original
    assert tournament.cover_image.storage.exists(original)
