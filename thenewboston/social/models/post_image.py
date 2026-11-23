from django.db import models

from thenewboston.general.models import CreatedModified


class PostImage(CreatedModified):
    owner = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='post_images')
    # Images are uploaded one request at a time before the post is saved, so an image has no post until the post
    # that lists it is created or updated. Images that never get one are removed by `delete_unattached_post_images`.
    post = models.ForeignKey('social.Post', on_delete=models.CASCADE, related_name='images', blank=True, null=True)
    image = models.ImageField(upload_to='images/')
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ('position', 'id')
        indexes = [
            models.Index(
                fields=['created_date'],
                condition=models.Q(post__isnull=True),
                name='unattached_post_image_idx',
            ),
        ]

    def __str__(self):
        return f'Image {self.pk} of post {self.post_id}' if self.post_id else f'Unattached image {self.pk}'
