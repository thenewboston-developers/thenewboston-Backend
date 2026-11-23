from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from ..models import PostImage
from ..serializers.post_image import PostImageReadSerializer, PostImageWriteSerializer


class PostImageViewSet(GenericViewSet):
    """
    Upload of one image for a post that is about to be created or updated.

    The returned id is then listed in `image_ids` of the post. Images are uploaded one request at a time, so the size
    of a request does not grow with the number of images of the post.
    """

    parser_classes = (MultiPartParser, FormParser)
    permission_classes = [IsAuthenticated]
    queryset = PostImage.objects.none()
    serializer_class = PostImageWriteSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        post_image = serializer.save()
        read_serializer = PostImageReadSerializer(post_image, context={'request': request})

        return Response(read_serializer.data, status=status.HTTP_201_CREATED)
