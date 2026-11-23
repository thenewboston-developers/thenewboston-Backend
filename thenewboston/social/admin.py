from django.contrib import admin

from .models import Comment, Follower, Post, PostImage, PostLike

admin.site.register(Comment)


@admin.register(Follower)
class FollowerAdmin(admin.ModelAdmin):
    list_select_related = ('follower', 'following')


class PostImageInline(admin.TabularInline):
    extra = 0
    model = PostImage
    raw_id_fields = ('owner',)


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    inlines = (PostImageInline,)


@admin.register(PostImage)
class PostImageAdmin(admin.ModelAdmin):
    list_display = ('id', 'post', 'owner', 'position', 'created_date')
    list_select_related = ('owner', 'post')
    raw_id_fields = ('owner', 'post')


@admin.register(PostLike)
class PostLikeAdmin(admin.ModelAdmin):
    list_select_related = ('user', 'post')
