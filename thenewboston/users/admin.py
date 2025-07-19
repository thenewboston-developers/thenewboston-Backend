from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User, UserAgreement


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = UserAdmin.list_display
    fieldsets = UserAdmin.fieldsets + (
        ('Profile', {
            'fields': ('avatar', 'bio')
        }),
        (
            'Social Media', {
                'fields': (
                    'discord_username', 'facebook_username', 'github_username', 'instagram_username',
                    'linkedin_username', 'pinterest_username', 'reddit_username', 'tiktok_username', 'twitch_username',
                    'x_username', 'youtube_username'
                )
            }
        ),
    )
    list_filter = UserAdmin.list_filter


admin.site.register(UserAgreement)
