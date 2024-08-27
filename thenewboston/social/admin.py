from django.contrib import admin

from .models import Comment, Follower, Post, PostReaction

admin.site.register(Comment)
admin.site.register(Follower)
admin.site.register(Post)
admin.site.register(PostReaction)
