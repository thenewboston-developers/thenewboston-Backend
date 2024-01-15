from django.contrib import admin

from .models import GitHubUser, Issue, Pull, Repo

admin.site.register(GitHubUser)
admin.site.register(Issue)
admin.site.register(Pull)
admin.site.register(Repo)
