from django.contrib import admin

from .models import Comment, Follower, Post

admin.site.register(Comment)
admin.site.register(Follower)
admin.site.register(Post)
