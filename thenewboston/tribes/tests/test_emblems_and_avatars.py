"""Uploaded tribe emblems and the player avatars that travel with the game state."""

from datetime import timedelta
from io import BytesIO

import pytest
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from model_bakery import baker
from PIL import Image

from thenewboston.tribes.models import Activity

from .test_integrity import action, client_for, snapshot

pytestmark = pytest.mark.django_db
MEDIA = 'http://testserver/media/'


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    settings.MEDIA_URL = '/media/'
    return tmp_path


def picture(size=(512, 512), name='emblem.png'):
    buffer = BytesIO()
    Image.new('RGB', size, 'red').save(buffer, format='PNG')
    return SimpleUploadedFile(name, buffer.getvalue(), content_type='image/png')


def upload(client, season, image=None, *, expected=200):
    data = {'season_id': season.pk, 'image': image or picture()}
    response = client.post('/api/tribes/emblem', data, format='multipart')
    assert response.status_code == expected, response.data
    return response.data


def tribe_of(state, tribe_id):
    return next(t for t in state['tribes'] if t['id'] == tribe_id)


def stored_files(media_root):
    return [path for path in media_root.rglob('*') if path.is_file()]


def test_founder_uploads_a_square_emblem_that_everyone_sees(tribes_game, media_root):
    game = tribes_game
    assert tribe_of(snapshot(game['alice'], game['season']), game['alice_tribe'])['emblem_image'] is None

    state = upload(game['alice'], game['season'])

    address = tribe_of(state, game['alice_tribe'])['emblem_image']
    assert address.startswith(f'{MEDIA}images/') and address.endswith('.png')
    assert default_storage.exists(address.removeprefix(MEDIA))
    assert tribe_of(state, game['bob_tribe'])['emblem_image'] is None
    for viewer in (game['bob'], client_for()):
        assert tribe_of(snapshot(viewer, game['season']), game['alice_tribe'])['emblem_image'] == address
    assert Activity.objects.filter(tribe_id=game['alice_tribe'], text='Changed the tribe emblem.').count() == 1
    # The emoji of older tribes stays as the fallback for anything that cannot show a picture
    assert tribe_of(state, game['alice_tribe'])['emblem'] == '🐺'


def test_a_new_upload_replaces_the_emblem(tribes_game):
    game = tribes_game
    first = tribe_of(upload(game['alice'], game['season']), game['alice_tribe'])['emblem_image']
    second = tribe_of(upload(game['alice'], game['season']), game['alice_tribe'])['emblem_image']
    assert first != second
    assert tribe_of(snapshot(game['bob'], game['season']), game['alice_tribe'])['emblem_image'] == second


@pytest.mark.parametrize('size', [(511, 512), (512, 256), (1024, 1024), (64, 64)])
def test_emblem_must_be_exactly_512_pixels_square(tribes_game, media_root, size):
    game = tribes_game
    data = upload(game['alice'], game['season'], picture(size), expected=400)
    assert [error['message'] for error in data['image']] == [
        f'Image must be exactly 512x512 pixels. Got {size[0]}x{size[1]}.'
    ]
    assert tribe_of(snapshot(game['alice'], game['season']), game['alice_tribe'])['emblem_image'] is None
    assert not stored_files(media_root)


def test_emblem_must_be_an_image(tribes_game, media_root):
    game = tribes_game
    file = SimpleUploadedFile('emblem.png', b'not an image', content_type='image/png')
    upload(game['alice'], game['season'], file, expected=400)
    response = game['alice'].post('/api/tribes/emblem', {'season_id': game['season'].pk}, format='multipart')
    assert response.status_code == 400
    assert not stored_files(media_root)


def test_only_the_founder_may_change_the_emblem(tribes_game, media_root):
    game = tribes_game
    member = baker.make('users.User', username='recruit')
    action(client_for(member), game['season'], 'apply', tribe_id=game['alice_tribe'])
    action(game['alice'], game['season'], 'accept_application', user_id=member.pk)

    upload(client_for(member), game['season'], expected=403)
    upload(client_for(baker.make('users.User')), game['season'], expected=403)
    upload(client_for(), game['season'], expected=401)

    assert tribe_of(snapshot(game['alice'], game['season']), game['alice_tribe'])['emblem_image'] is None
    # A refused upload never reaches storage
    assert not stored_files(media_root)


def test_emblem_can_change_during_the_season_but_not_after_it(active_game, media_root):
    game = active_game
    season = game['season']
    state = upload(game['alice'], season)
    address = tribe_of(state, game['alice_tribe'])['emblem_image']
    assert address

    season.refresh_from_db()
    season.starts_at = timezone.now() - timedelta(days=8)
    season.ends_at = timezone.now() - timedelta(seconds=1)
    season.save(update_fields=['starts_at', 'ends_at'])
    upload(game['alice'], season, expected=400)

    # The finished season keeps its emblem in the archive
    finished = snapshot(game['bob'], season)
    assert finished['season']['status'] == 'finished'
    assert tribe_of(finished, game['alice_tribe'])['emblem_image'] == address
    assert len(stored_files(media_root)) == 1


def test_unknown_season_is_reported(tribes_game):
    game = tribes_game
    response = game['alice'].post(
        '/api/tribes/emblem', {'season_id': game['season'].pk + 1000, 'image': picture()}, format='multipart'
    )
    assert response.status_code == 404


def test_editing_tribe_details_keeps_the_emblem(tribes_game):
    game = tribes_game
    address = tribe_of(upload(game['alice'], game['season']), game['alice_tribe'])['emblem_image']

    state = action(game['alice'], game['season'], 'update_tribe', name='Iron Wolves', color='#123456', motto='Howl')

    tribe = tribe_of(state, game['alice_tribe'])
    assert (tribe['emblem'], tribe['emblem_image'], tribe['color'], tribe['motto']) == (
        '🐺',
        address,
        '#123456',
        'Howl',
    )
    # Older clients still send the emoji field, and a tribe founded without one gets the default
    state = action(game['alice'], game['season'], 'update_tribe', name='Iron Wolves', emblem='🦊')
    assert tribe_of(state, game['alice_tribe'])['emblem'] == '🦊'
    founder = client_for(baker.make('users.User'))
    assert tribe_of(action(founder, game['season'], 'create_tribe', name='Plain'), 3)['emblem'] == '🛡️'


def test_players_carry_their_current_avatar(tribes_game):
    game = tribes_game
    alice, bob = game['alice_wallet'].owner, game['bob_wallet'].owner
    alice.avatar = 'images/alice.png'
    alice.save(update_fields=['avatar'])
    applicant = baker.make('users.User', username='applicant', avatar='images/applicant.png')
    baker.make('users.User', username='invited', avatar='images/invited.png')
    action(client_for(applicant), game['season'], 'apply', tribe_id=game['alice_tribe'])
    action(game['alice'], game['season'], 'invite', username='invited')
    action(game['alice'], game['season'], 'message', text='Hello', to_tribe_id=game['bob_tribe'])
    action(game['bob'], game['season'], 'message', text='Hi', to_tribe_id=game['alice_tribe'])

    state = snapshot(game['alice'], game['season'])

    own, rival = tribe_of(state, game['alice_tribe']), tribe_of(state, game['bob_tribe'])
    assert own['members'] == [{'id': alice.pk, 'username': 'bucky', 'avatar': f'{MEDIA}images/alice.png'}]
    assert rival['members'] == [{'id': bob.pk, 'username': 'dmitry', 'avatar': None}]
    assert own['applications'][0]['avatar'] == f'{MEDIA}images/applicant.png'
    assert own['invites'][0]['avatar'] == f'{MEDIA}images/invited.png'
    assert state['viewer']['avatar'] == f'{MEDIA}images/alice.png'
    assert [(m['username'], m['avatar']) for m in state['messages']] == [
        ('bucky', f'{MEDIA}images/alice.png'),
        ('dmitry', None),
    ]
    assert {(a['username'], a['avatar']) for a in state['activity']} == {
        ('applicant', f'{MEDIA}images/applicant.png'),
        ('bucky', f'{MEDIA}images/alice.png'),
    }
    assert snapshot(game['bob'], game['season'])['viewer']['avatar'] is None
    assert snapshot(client_for(), game['season'])['viewer'] is None

    # The avatar is read when the state is built, so a new picture shows without touching the season
    bob.avatar = 'images/bob.png'
    bob.save(update_fields=['avatar'])
    state = snapshot(game['alice'], game['season'])
    assert tribe_of(state, game['bob_tribe'])['members'][0]['avatar'] == f'{MEDIA}images/bob.png'
    assert state['messages'][1]['avatar'] == f'{MEDIA}images/bob.png'


def test_older_messages_and_activity_carry_avatars(tribes_game):
    game = tribes_game
    alice = game['alice_wallet'].owner
    alice.avatar = 'images/alice.png'
    alice.save(update_fields=['avatar'])
    action(game['alice'], game['season'], 'message', text='Hello', to_tribe_id=game['bob_tribe'])
    Activity.objects.create(season=game['season'], tribe_id=game['alice_tribe'], user=None, text='The season began.')
    state = snapshot(game['alice'], game['season'])
    parameters = {'season_id': game['season'].pk}

    messages = game['alice'].get('/api/tribes/messages', {**parameters, 'before': state['messages'][-1]['id'] + 1})
    activity = game['alice'].get('/api/tribes/activity', {**parameters, 'before': state['activity'][0]['id'] + 1})

    assert [m['avatar'] for m in messages.data['results']] == [f'{MEDIA}images/alice.png']
    assert [(a['username'], a['avatar']) for a in activity.data['results']][:2] == [
        ('Tribes', None),
        ('bucky', f'{MEDIA}images/alice.png'),
    ]
    # Rivals read the same correspondence with the sender's avatar
    messages = game['bob'].get('/api/tribes/messages', parameters)
    assert [m['avatar'] for m in messages.data['results']] == [f'{MEDIA}images/alice.png']
