from django.db import models

from thenewboston.general.models import CreatedModified


class Post(CreatedModified):
    owner = models.ForeignKey('users.User', on_delete=models.CASCADE)
    content = models.TextField()
    # Deprecated: the images of a post are `PostImage` rows (`post.images`) and this column is no longer read or
    # written. It still holds the values that were copied to `PostImage`, so the release that introduced `PostImage`
    # can be rolled back. TODO: Drop the column once that release has proven stable.
    image = models.ImageField(upload_to='images/', blank=True)
    recipient = models.ForeignKey(
        'users.User', on_delete=models.CASCADE, related_name='received_posts', blank=True, null=True
    )
    price_amount = models.PositiveBigIntegerField(blank=True, null=True)
    price_currency = models.ForeignKey('currencies.Currency', blank=True, null=True, on_delete=models.SET_NULL)
    mentioned_users = models.ManyToManyField('users.User', related_name='mentioned_in_posts', blank=True)

    def __str__(self):
        return self.content[:50]

    @property
    def cover_image(self):
        """The first image of the post: the one that notification thumbnails and single-image API clients show."""
        # `all()` is served from the prefetch cache when the post was loaded with its images
        post_image = next(iter(self.images.all()), None)
        return post_image.image if post_image else None
