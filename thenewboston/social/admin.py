from django.contrib import admin

from .models import Comment, Follower, Post, PostLike

admin.site.register(Comment)
admin.site.register(Follower)
admin.site.register(Post)
admin.site.register(PostLike)
