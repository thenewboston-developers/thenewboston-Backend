from django.db import models


class SocialMediaMixin(models.Model):
    discord_username = models.CharField(max_length=255, null=True, blank=True)
    facebook_username = models.CharField(max_length=255, null=True, blank=True)
    github_username = models.CharField(max_length=255, null=True, blank=True)
    instagram_username = models.CharField(max_length=255, null=True, blank=True)
    linkedin_username = models.CharField(max_length=255, null=True, blank=True)
    pinterest_username = models.CharField(max_length=255, null=True, blank=True)
    reddit_username = models.CharField(max_length=255, null=True, blank=True)
    tiktok_username = models.CharField(max_length=255, null=True, blank=True)
    twitch_username = models.CharField(max_length=255, null=True, blank=True)
    x_username = models.CharField(max_length=255, null=True, blank=True)
    youtube_username = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        abstract = True
