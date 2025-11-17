from django.contrib import admin

from .models import Bonsai, BonsaiHighlight, BonsaiImage


@admin.register(Bonsai)
class BonsaiAdmin(admin.ModelAdmin):
    list_display = ('name', 'species', 'genus', 'cultivar', 'status', 'price_amount', 'price_currency', 'slug')
    list_filter = ('status', 'price_currency', 'genus')
    search_fields = ('name', 'species', 'genus', 'cultivar', 'slug')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(BonsaiHighlight)
class BonsaiHighlightAdmin(admin.ModelAdmin):
    list_display = ('bonsai', 'order', 'text')
    list_filter = ('bonsai',)
    search_fields = ('bonsai__name', 'text')


@admin.register(BonsaiImage)
class BonsaiImageAdmin(admin.ModelAdmin):
    list_display = ('bonsai', 'order', 'url')
    list_filter = ('bonsai',)
    search_fields = ('bonsai__name', 'url')
