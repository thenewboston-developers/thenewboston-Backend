from datetime import timedelta
from io import BytesIO
from unittest.mock import patch

import pytest
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from model_bakery import baker
from PIL import Image

from thenewboston.notifications.models import Notification
from thenewboston.social.constants import (
    MAX_POST_IMAGES,
    MAX_UNATTACHED_POST_IMAGES_PER_USER,
    UNATTACHED_POST_IMAGE_LIFETIME,
)
from thenewboston.social.models import Post, PostImage
from thenewboston.social.tasks import delete_unattached_post_images_task


def make_image_file(name='photo.png'):
    buffer = BytesIO()
    Image.new('RGB', (4, 4), 'red').save(buffer, format='PNG')
    return SimpleUploadedFile(name, buffer.getvalue(), content_type='image/png')


def make_post_image(owner, post=None, position=0):
    return PostImage.objects.create(owner=owner, post=post, position=position, image=make_image_file())


def image_ids_of(post):
    return list(post.images.values_list('id', flat=True))


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


@pytest.mark.django_db
class TestPostImageUpload:
    def test_upload_returns_the_id_and_url_of_an_unattached_image(self, authenticated_api_client, bucky):
        response = authenticated_api_client.post('/api/post-images', {'image': make_image_file()}, format='multipart')

        assert response.status_code == 201
        post_image = PostImage.objects.get()
        assert response.data == {'id': post_image.id, 'image': post_image.image.url}
        assert post_image.owner == bucky
        assert post_image.post is None
        assert default_storage.exists(post_image.image.name)

    def test_upload_requires_authentication(self, api_client):
        response = api_client.post('/api/post-images', {'image': make_image_file()}, format='multipart')

        assert response.status_code == 401
        assert not PostImage.objects.exists()

    def test_upload_rejects_a_file_that_is_not_an_image(self, authenticated_api_client):
        file = SimpleUploadedFile('notes.png', b'not an image', content_type='image/png')

        response = authenticated_api_client.post('/api/post-images', {'image': file}, format='multipart')

        assert response.status_code == 400
        assert 'image' in response.data
        assert not PostImage.objects.exists()

    def test_upload_is_refused_while_too_many_images_are_unattached(self, authenticated_api_client, bucky, dmitry):
        post = baker.make(Post, owner=bucky)
        baker.make(PostImage, owner=bucky, post=post, _quantity=MAX_UNATTACHED_POST_IMAGES_PER_USER)
        baker.make(PostImage, owner=dmitry, post=None, _quantity=MAX_UNATTACHED_POST_IMAGES_PER_USER)
        baker.make(PostImage, owner=bucky, post=None, _quantity=MAX_UNATTACHED_POST_IMAGES_PER_USER - 1)

        def upload():
            return authenticated_api_client.post('/api/post-images', {'image': make_image_file()}, format='multipart')

        assert upload().status_code == 201
        response = upload()
        assert response.status_code == 400
        assert 'non_field_errors' in response.data


@pytest.mark.django_db
class TestPostImages:
    def test_create_attaches_the_images_in_the_given_order(self, authenticated_api_client, bucky):
        first, second, third = (make_post_image(bucky) for _ in range(3))
        unused = make_post_image(bucky)

        response = authenticated_api_client.post(
            '/api/posts', {'content': 'Photos', 'image_ids': [third.id, first.id, second.id]}, format='json'
        )

        assert response.status_code == 201
        post = Post.objects.get(pk=response.data['id'])
        assert image_ids_of(post) == [third.id, first.id, second.id]
        assert [image['id'] for image in response.data['images']] == [third.id, first.id, second.id]
        assert response.data['images'][0]['image'] == third.image.url
        assert response.data['image'] == response.data['images'][0]['image']
        unused.refresh_from_db()
        assert unused.post is None

    def test_create_sends_coins_with_images(
        self, authenticated_api_client, bucky, dmitry, tnb_currency, bucky_tnb_wallet
    ):
        first, second = (make_post_image(bucky) for _ in range(2))

        with patch('thenewboston.notifications.models.notification.Notification.stream'):
            response = authenticated_api_client.post(
                '/api/posts',
                {
                    'content': 'Coins and photos',
                    'image_ids': [second.id, first.id],
                    'price_amount': '5',
                    'price_currency': tnb_currency.id,
                    'recipient': dmitry.id,
                },
                format='json',
            )

        assert response.status_code == 201
        assert [image['id'] for image in response.data['images']] == [second.id, first.id]
        assert response.data['price_amount'] == 5
        bucky_tnb_wallet.refresh_from_db()
        assert bucky_tnb_wallet.balance == 995
        payload = Notification.objects.get(owner=dmitry).payload
        assert payload['notification_type'] == 'POST_COIN_TRANSFER'
        assert payload['post_image_thumbnail'] == second.image.url

    def test_create_without_images(self, authenticated_api_client):
        response = authenticated_api_client.post('/api/posts', {'content': 'Just text'}, format='json')

        assert response.status_code == 201
        assert response.data['image'] is None
        assert response.data['images'] == []

    @pytest.mark.parametrize('case', ['other_owner', 'other_post', 'missing'])
    def test_create_rejects_images_the_user_cannot_attach(self, authenticated_api_client, bucky, dmitry, case):
        own_image = make_post_image(bucky)
        if case == 'other_owner':
            image_id = make_post_image(dmitry).id
        elif case == 'other_post':
            image_id = make_post_image(bucky, post=baker.make(Post, owner=bucky)).id
        else:
            image_id = own_image.id + 1000

        response = authenticated_api_client.post(
            '/api/posts', {'content': 'Photos', 'image_ids': [own_image.id, image_id]}, format='json'
        )

        assert response.status_code == 400
        assert response.data['image_ids'][0]['message'] == f'Invalid image ids: {image_id}'
        assert not Post.objects.filter(content='Photos').exists()
        own_image.refresh_from_db()
        assert own_image.post is None

    def test_create_rejects_an_image_listed_twice(self, authenticated_api_client, bucky):
        image = make_post_image(bucky)

        response = authenticated_api_client.post(
            '/api/posts', {'content': 'Photos', 'image_ids': [image.id, image.id]}, format='json'
        )

        assert response.status_code == 400
        assert 'image_ids' in response.data

    def test_create_rejects_more_images_than_a_post_can_have(self, authenticated_api_client, bucky):
        images = baker.make(PostImage, owner=bucky, post=None, _quantity=MAX_POST_IMAGES + 1)

        response = authenticated_api_client.post(
            '/api/posts', {'content': 'Photos', 'image_ids': [image.id for image in images]}, format='json'
        )

        assert response.status_code == 400
        assert 'image_ids' in response.data
        assert not Post.objects.exists()

    def test_update_reorders_adds_and_removes_images(self, authenticated_api_client, bucky):
        post = baker.make(Post, owner=bucky)
        kept, removed, moved = (make_post_image(bucky, post=post, position=position) for position in range(3))
        added = make_post_image(bucky)

        response = authenticated_api_client.patch(
            f'/api/posts/{post.id}', {'image_ids': [moved.id, added.id, kept.id]}, format='json'
        )

        assert response.status_code == 200
        assert [image['id'] for image in response.data['images']] == [moved.id, added.id, kept.id]
        assert image_ids_of(post) == [moved.id, added.id, kept.id]
        assert not PostImage.objects.filter(pk=removed.pk).exists()

    @pytest.mark.parametrize('request_format', ['json', 'multipart'])
    def test_update_without_image_fields_keeps_the_images(self, authenticated_api_client, bucky, request_format):
        post = baker.make(Post, owner=bucky)
        images = [make_post_image(bucky, post=post, position=position) for position in range(2)]

        response = authenticated_api_client.patch(f'/api/posts/{post.id}', {'content': 'Edited'}, format=request_format)

        assert response.status_code == 200
        assert response.data['content'] == 'Edited'
        assert image_ids_of(post) == [image.id for image in images]

    def test_update_with_an_empty_list_removes_every_image(self, authenticated_api_client, bucky):
        post = baker.make(Post, owner=bucky)
        for position in range(2):
            make_post_image(bucky, post=post, position=position)

        response = authenticated_api_client.patch(f'/api/posts/{post.id}', {'image_ids': []}, format='json')

        assert response.status_code == 200
        assert response.data['image'] is None
        assert response.data['images'] == []
        assert not post.images.exists()

    def test_update_cannot_take_an_image_of_another_user(self, authenticated_api_client, bucky, dmitry):
        post = baker.make(Post, owner=bucky)
        own_image = make_post_image(bucky, post=post)
        other_image = make_post_image(dmitry)

        response = authenticated_api_client.patch(
            f'/api/posts/{post.id}', {'image_ids': [own_image.id, other_image.id]}, format='json'
        )

        assert response.status_code == 400
        assert response.data['image_ids'][0]['message'] == f'Invalid image ids: {other_image.id}'
        assert image_ids_of(post) == [own_image.id]
        other_image.refresh_from_db()
        assert other_image.post is None

    def test_update_cannot_take_an_image_from_another_post(self, authenticated_api_client, bucky):
        post, other_post = baker.make(Post, owner=bucky, _quantity=2)
        own_image = make_post_image(bucky, post=post)
        other_image = make_post_image(bucky, post=other_post)

        response = authenticated_api_client.patch(
            f'/api/posts/{post.id}', {'image_ids': [own_image.id, other_image.id]}, format='json'
        )

        assert response.status_code == 400
        assert response.data['image_ids'][0]['message'] == f'Invalid image ids: {other_image.id}'
        assert image_ids_of(other_post) == [other_image.id]

    def test_has_image_filter(self, authenticated_api_client, bucky):
        with_images, without_images = baker.make(Post, owner=bucky, _quantity=2)
        for position in range(2):
            make_post_image(bucky, post=with_images, position=position)

        def get_post_ids(has_image):
            response = authenticated_api_client.get(f'/api/posts?has_image={has_image}')
            assert response.status_code == 200
            return [post['id'] for post in response.data['results']]

        assert get_post_ids('true') == [with_images.id]
        assert get_post_ids('false') == [without_images.id]

    def test_post_queries_do_not_grow_with_images(self, authenticated_api_client, bucky):
        def get_posts():
            with CaptureQueriesContext(connection) as queries:
                response = authenticated_api_client.get('/api/posts')
            assert response.status_code == 200
            return response.data['results'], len(queries)

        post = baker.make(Post, owner=bucky)
        make_post_image(bucky, post=post)
        _, single_count = get_posts()
        for _ in range(3):
            post = baker.make(Post, owner=bucky)
            for position in range(3):
                make_post_image(bucky, post=post, position=position)

        posts, page_count = get_posts()

        assert page_count == single_count
        assert [len(post['images']) for post in posts] == [3, 3, 3, 1]

    def test_notification_thumbnail_is_the_first_image(self, authenticated_api_client, bucky, dmitry):
        post = baker.make(Post, owner=dmitry)
        make_post_image(dmitry, post=post, position=1)
        first = make_post_image(dmitry, post=post, position=0)

        with patch('thenewboston.social.views.post_like.NotificationConsumer.stream_notification'):
            response = authenticated_api_client.post(f'/api/posts/{post.id}/like')

        assert response.status_code == 201
        payload = Notification.objects.get(owner=dmitry).payload
        assert payload['post_image_thumbnail'] == first.image.url


@pytest.mark.django_db
class TestSingleImageApi:
    """The `image` and `clear_image` fields that clients used before posts could have several images."""

    def test_create_with_an_image_file(self, authenticated_api_client, bucky):
        response = authenticated_api_client.post(
            '/api/posts', {'content': 'Photo', 'image': make_image_file()}, format='multipart'
        )

        assert response.status_code == 201
        post_image = PostImage.objects.get()
        assert post_image.owner == bucky
        assert post_image.post_id == response.data['id']
        assert response.data['image'] == post_image.image.url
        assert response.data['images'] == [{'id': post_image.id, 'image': response.data['image']}]

    def test_create_sends_coins_with_an_image_file(
        self, authenticated_api_client, bucky, dmitry, tnb_currency, bucky_tnb_wallet
    ):
        with patch('thenewboston.notifications.models.notification.Notification.stream'):
            response = authenticated_api_client.post(
                '/api/posts',
                {
                    'content': 'Coins and a photo',
                    'image': make_image_file(),
                    'price_amount': '5',
                    'price_currency': str(tnb_currency.id),
                    'recipient': str(dmitry.id),
                },
                format='multipart',
            )

        assert response.status_code == 201
        post_image = PostImage.objects.get()
        assert response.data['image'] == post_image.image.url
        bucky_tnb_wallet.refresh_from_db()
        assert bucky_tnb_wallet.balance == 995
        assert Notification.objects.get(owner=dmitry).payload['post_image_thumbnail'] == post_image.image.url

    def test_update_with_an_empty_image_field_keeps_the_images(self, authenticated_api_client, bucky):
        post = baker.make(Post, owner=bucky)
        images = [make_post_image(bucky, post=post, position=position) for position in range(2)]

        response = authenticated_api_client.patch(
            f'/api/posts/{post.id}', {'content': 'Edited', 'image': ''}, format='multipart'
        )

        assert response.status_code == 200
        assert image_ids_of(post) == [image.id for image in images]

    def test_update_with_an_image_file_replaces_the_first_image(self, authenticated_api_client, bucky):
        post = baker.make(Post, owner=bucky)
        first, second = (make_post_image(bucky, post=post, position=position) for position in range(2))
        previous_name = first.image.name

        response = authenticated_api_client.patch(
            f'/api/posts/{post.id}', {'image': make_image_file()}, format='multipart'
        )

        assert response.status_code == 200
        assert image_ids_of(post) == [first.id, second.id]
        first.refresh_from_db()
        assert first.image.name != previous_name
        assert response.data['image'] == first.image.url

    def test_update_with_an_image_file_gives_a_post_its_first_image(self, authenticated_api_client, bucky):
        post = baker.make(Post, owner=bucky)

        response = authenticated_api_client.patch(
            f'/api/posts/{post.id}', {'image': make_image_file()}, format='multipart'
        )

        assert response.status_code == 200
        assert len(response.data['images']) == 1
        assert response.data['image'] == response.data['images'][0]['image']

    def test_clear_image_removes_the_first_image(self, authenticated_api_client, bucky):
        post = baker.make(Post, owner=bucky)
        first, second = (make_post_image(bucky, post=post, position=position) for position in range(2))

        response = authenticated_api_client.patch(
            f'/api/posts/{post.id}', {'content': 'Edited', 'clear_image': 'true'}, format='multipart'
        )

        assert response.status_code == 200
        assert image_ids_of(post) == [second.id]
        assert response.data['image'] == second.image.url

    def test_image_ids_cannot_be_combined_with_the_single_image_fields(self, authenticated_api_client, bucky):
        post = baker.make(Post, owner=bucky)
        image = make_post_image(bucky)

        response = authenticated_api_client.patch(
            f'/api/posts/{post.id}', {'image_ids': [image.id], 'clear_image': True}, format='json'
        )

        assert response.status_code == 400
        assert 'non_field_errors' in response.data
        assert not post.images.exists()


@pytest.mark.django_db
class TestDeleteUnattachedPostImages:
    @staticmethod
    def make_image(owner, *, age, post=None):
        post_image = make_post_image(owner, post=post)
        PostImage.objects.filter(pk=post_image.pk).update(created_date=timezone.now() - age)
        return post_image

    def test_only_expired_unattached_images_are_deleted(self, bucky):
        expired_age = UNATTACHED_POST_IMAGE_LIFETIME + timedelta(minutes=1)
        post = baker.make(Post, owner=bucky)
        expired = self.make_image(bucky, age=expired_age)
        recent = self.make_image(bucky, age=UNATTACHED_POST_IMAGE_LIFETIME - timedelta(minutes=1))
        attached = self.make_image(bucky, age=expired_age, post=post)

        delete_unattached_post_images_task()

        assert set(PostImage.objects.values_list('id', flat=True)) == {recent.id, attached.id}
        assert not default_storage.exists(expired.image.name)
        assert default_storage.exists(recent.image.name)
        assert default_storage.exists(attached.image.name)

    def test_a_file_that_cannot_be_deleted_does_not_stop_the_task(self, bucky):
        expired_age = UNATTACHED_POST_IMAGE_LIFETIME + timedelta(minutes=1)
        for _ in range(2):
            self.make_image(bucky, age=expired_age)

        with patch.object(default_storage, 'delete', side_effect=OSError('storage is unavailable')) as delete:
            delete_unattached_post_images_task()

        assert delete.call_count == 2
        assert not PostImage.objects.exists()


@pytest.fixture
def migrate_social():
    """Takes the `social` tables to a migration (the latest by default) and returns the models as they were then."""

    def migrate(name=None):
        executor = MigrationExecutor(connection)
        targets = [('social', name)] if name else executor.loader.graph.leaf_nodes()
        executor.migrate(targets)
        return executor.loader.project_state(targets).apps

    yield migrate
    migrate()


# The migrations change the schema, which a test that runs inside a transaction must not do
@pytest.mark.django_db(transaction=True)
def test_migration_copies_the_image_of_each_post(bucky, dmitry, migrate_social):
    # The `Post.image` column that the migration reads exists only in the historical models
    apps = migrate_social('0007_post_image')
    HistoricalPost, HistoricalPostImage = apps.get_model('social', 'Post'), apps.get_model('social', 'PostImage')
    with_image = HistoricalPost.objects.create(owner_id=bucky.id, content='First', image='images/first.png')
    HistoricalPost.objects.create(owner_id=bucky.id, content='No image', image='')
    already_copied = HistoricalPost.objects.create(owner_id=dmitry.id, content='Second', image='images/second.png')
    existing = HistoricalPostImage.objects.create(
        owner_id=dmitry.id, post_id=already_copied.id, image='images/second.png'
    )

    migrate_social('0008_copy_post_images')

    copied = HistoricalPostImage.objects.exclude(pk=existing.pk).get()
    assert (copied.post_id, copied.owner_id, copied.image.name, copied.position) == (
        with_image.id,
        bucky.id,
        'images/first.png',
        0,
    )

    # Dropping the column leaves the copied images in place
    migrate_social()

    assert PostImage.objects.count() == 2
    assert Post.objects.get(pk=with_image.pk).cover_image.name == 'images/first.png'
    assert Post.objects.get(pk=already_copied.pk).cover_image.name == 'images/second.png'
