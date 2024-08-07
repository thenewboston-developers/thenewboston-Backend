from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = UserAdmin.list_display + ('discord_user_id', 'discord_username')
    fieldsets = UserAdmin.fieldsets + ((
        'Misc', {
            'fields': (
                'manual_contribution_reward_daily_limit', 'is_manual_contribution_allowed', 'discord_user_id',
                'discord_username'
            )
        }
    ),)
    list_filter = ('is_manual_contribution_allowed',) + UserAdmin.list_filter
