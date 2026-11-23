from typing import List, Sequence

from rest_framework import serializers

from thenewboston.general.utils.image import process_image

from ..models import PostImage


def get_post_image_thumbnail(post, request):
    cover_image = post.cover_image
    return request.build_absolute_uri(cover_image.url) if cover_image else None


def get_images_for_post(*, image_ids: Sequence[int], user, post=None) -> List[PostImage]:
    """
    Return the images with the given ids in the given order, locked until the end of the transaction.

    Each of them must have been uploaded by the user and must either be unattached or belong to the post already.
    """
    if len(set(image_ids)) != len(image_ids):
        raise serializers.ValidationError({'image_ids': ['Each image can be listed only once.']})

    images_by_id = {image.id: image for image in PostImage.objects.select_for_update().filter(id__in=image_ids)}
    unavailable_ids = [
        str(image_id)
        for image_id in image_ids
        if (image := images_by_id.get(image_id)) is None
        or image.owner_id != user.id
        or (image.post_id is not None and (post is None or image.post_id != post.id))
    ]
    if unavailable_ids:
        raise serializers.ValidationError({'image_ids': [f'Invalid image ids: {", ".join(unavailable_ids)}']})

    return [images_by_id[image_id] for image_id in image_ids]


def set_post_images(*, post, images: Sequence[PostImage]):
    """Make the given images the images of the post, in the given order. The images it had besides them are removed."""
    post.images.exclude(id__in=[image.id for image in images]).delete()

    for position, image in enumerate(images):
        image.post = post
        image.position = position

    PostImage.objects.bulk_update(images, ['post', 'position'])


def replace_cover_image(*, post, image_file):
    """Single-image API: replace the first image of the post or give the post its first image."""
    cover = post.images.first()
    if cover is None:
        return PostImage.objects.create(owner=post.owner, post=post, image=process_image(image_file), position=0)

    cover.image = process_image(image_file)
    cover.save(update_fields=['image', 'modified_date'])
    return cover


def remove_cover_image(*, post):
    """Single-image API: remove the first image of the post."""
    cover = post.images.first()
    if cover is not None:
        cover.delete()
