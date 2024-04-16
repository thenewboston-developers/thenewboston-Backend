from django.contrib import admin

from .models import Course, Lecture


class LectureInline(admin.TabularInline):
    model = Lecture
    extra = 1
    fields = [
        'name', 'description', 'publication_status', 'youtube_id', 'position', 'thumbnail_url', 'duration_seconds'
    ]


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ['name', 'description', 'publication_status', 'instructor', 'created_date']
    inlines = [LectureInline]
    search_fields = ['name', 'description', 'instructor__username']
    list_filter = ['publication_status', 'instructor']
    readonly_fields = ['created_date', 'modified_date']


@admin.register(Lecture)
class LectureAdmin(admin.ModelAdmin):
    list_display = ['name', 'course', 'youtube_id', 'position', 'duration_seconds', 'created_date']
    list_filter = ['course', 'publication_status']
    search_fields = ['name', 'youtube_id', 'description']
    readonly_fields = ['created_date', 'modified_date']
