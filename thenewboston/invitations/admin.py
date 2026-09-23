from django.contrib import admin

from .models import Invitation, InvitationLimit


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_select_related = ('recipient',)


@admin.register(InvitationLimit)
class InvitationLimitAdmin(admin.ModelAdmin):
    list_select_related = ('owner',)
