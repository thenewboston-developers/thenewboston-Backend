from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver

from thenewboston.general.models import CreatedModified
from thenewboston.general.utils.mentions import create_mention_notifications, get_mentioned_users


class Comment(CreatedModified):
    owner = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='comments')
    post = models.ForeignKey('social.Post', on_delete=models.CASCADE, related_name='comments')
    content = models.TextField()
    price_amount = models.PositiveBigIntegerField(blank=True, null=True)
    price_currency = models.ForeignKey('currencies.Currency', blank=True, null=True, on_delete=models.SET_NULL)
    mentioned_users = models.ManyToManyField('users.User', related_name='mentioned_in_comments', blank=True)

    def __str__(self):
        return self.content[:20]

    def extract_and_save_mentions(self):
        """Extract mentions from content and save them."""
        mentioned_users = get_mentioned_users(self.content)
        if mentioned_users:
            self.mentioned_users.set(mentioned_users)
            create_mention_notifications(
                mentioned_users=mentioned_users, mentioner=self.owner, content_type='comment', content_id=self.id
            )


@receiver(post_save, sender=Comment)
def handle_comment_mentions(sender, instance, created, **kwargs):
    """Extract and process mentions when a comment is created."""
    if created:
        instance.extract_and_save_mentions()
