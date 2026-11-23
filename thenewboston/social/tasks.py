import logging

from django.utils import timezone

from thenewboston.project.celery import app

from .constants import UNATTACHED_POST_IMAGE_LIFETIME
from .models import PostImage

logger = logging.getLogger(__name__)


@app.task(name='tasks.delete_unattached_post_images')
def delete_unattached_post_images_task():
    """Delete the images that were uploaded for a post but never became part of one, together with their files."""
    cutoff = timezone.now() - UNATTACHED_POST_IMAGE_LIFETIME
    expired_images = PostImage.objects.filter(post__isnull=True, created_date__lt=cutoff)

    for post_image in expired_images.iterator():
        # The row goes first and only while it is still unattached, so a post that claims the image at this very
        # moment either keeps it with its file or does not get it at all
        deleted_count, _ = PostImage.objects.filter(pk=post_image.pk, post__isnull=True).delete()
        if not deleted_count:
            continue

        try:
            post_image.image.storage.delete(post_image.image.name)
        except Exception:
            logger.warning('Unable to delete the file of unattached post image %s', post_image.pk, exc_info=True)
