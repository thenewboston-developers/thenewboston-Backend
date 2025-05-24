from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = UserAdmin.list_display
    fieldsets = UserAdmin.fieldsets
    list_filter = UserAdmin.list_filter
