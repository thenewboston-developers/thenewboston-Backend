from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('Discord', {
            'fields': ('discord_username',)
        }),
        ('Misc', {
            'fields': ('manual_contribution_reward_daily_limit', 'is_manual_contribution_allowed')
        }),
    )
    list_filter = ('is_manual_contribution_allowed',) + UserAdmin.list_filter
