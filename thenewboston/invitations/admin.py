from django.contrib import admin

from .models import Invitation, InvitationLimit

admin.site.register(Invitation)
admin.site.register(InvitationLimit)
