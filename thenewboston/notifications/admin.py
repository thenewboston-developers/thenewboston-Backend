from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('owner', 'is_read', 'created_date')
    list_filter = ('owner', 'is_read', 'created_date')
    readonly_fields = ('created_date', 'modified_date')
    search_fields = ('owner__username', 'owner__email', 'payload')
