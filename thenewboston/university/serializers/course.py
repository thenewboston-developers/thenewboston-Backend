from rest_framework import exceptions, serializers

from thenewboston.general.utils.image import process_image
from thenewboston.users.serializers.user import UserReadSerializer

from ..models import Course
from ..models.base import PublicationStatus


class CourseReadSerializer(serializers.ModelSerializer):
    instructor = UserReadSerializer(read_only=True)

    class Meta:
        model = Course
        fields = (
            'id',
            'name',
            'description',
            'publication_status',
            'thumbnail',
            'instructor',
            'created_date',
            'modified_date',
        )
        read_only_fields = (
            'id', 'name', 'description', 'publication_status', 'thumbnail', 'instructor', 'created_date',
            'modified_date'
        )


class CourseWriteSerializer(serializers.ModelSerializer):

    publication_status = serializers.BooleanField()

    class Meta:
        model = Course
        fields = ('name', 'description', 'thumbnail', 'publication_status')

    def create(self, validated_data):
        request = self.context.get('request')

        thumbnail = validated_data.get('thumbnail')
        if thumbnail:
            file = process_image(thumbnail)
            validated_data['thumbnail'] = file

        course = super().create({
            **validated_data,
            'instructor': request.user,
        })
        return course

    def update(self, instance, validated_data):
        request = self.context.get('request')
        if instance.instructor != request.user:
            raise exceptions.PermissionDenied('You do not have permission to edit this course.')
        return super().update(instance, validated_data)

    def validate_publication_status(self, value):
        if value:
            return PublicationStatus.PUBLISHED
        return PublicationStatus.DRAFT
