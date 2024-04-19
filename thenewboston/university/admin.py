from django.contrib import admin

from .models import Course, Lecture


class LectureInline(admin.TabularInline):
    extra = 1
    fields = (
        'name', 'description', 'publication_status', 'youtube_id', 'position', 'thumbnail_url', 'duration_seconds'
    )
    model = Lecture


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    inlines = (LectureInline,)
    list_display = ('name', 'description', 'publication_status', 'instructor', 'created_date')
    list_filter = ('publication_status', 'instructor')
    readonly_fields = ('created_date', 'modified_date')
    search_fields = ('name', 'description', 'instructor__username')


@admin.register(Lecture)
class LectureAdmin(admin.ModelAdmin):
    list_display = ('name', 'course', 'youtube_id', 'position', 'duration_seconds', 'created_date')
    list_filter = ('course', 'publication_status')
    readonly_fields = ('created_date', 'modified_date')
    search_fields = ('name', 'youtube_id', 'description')
