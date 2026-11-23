from datetime import timedelta

MAX_POST_IMAGES = 10
# An image is uploaded before the post it belongs to is saved, so a post whose submission is abandoned or fails
# leaves its uploads unattached. The limit bounds how many of those one user can accumulate.
MAX_UNATTACHED_POST_IMAGES_PER_USER = MAX_POST_IMAGES * 3
UNATTACHED_POST_IMAGE_LIFETIME = timedelta(hours=24)
