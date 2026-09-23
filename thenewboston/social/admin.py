from django.contrib import admin

from .models import Comment, Follower, Post, PostLike

admin.site.register(Comment)
admin.site.register(Post)


@admin.register(Follower)
class FollowerAdmin(admin.ModelAdmin):
    list_select_related = ('follower', 'following')


@admin.register(PostLike)
class PostLikeAdmin(admin.ModelAdmin):
    list_select_related = ('user', 'post')
