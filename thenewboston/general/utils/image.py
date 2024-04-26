import uuid
from pathlib import Path

from django.core.files.base import ContentFile


def process_image(image):
    """
    Process an image file to create a ContentFile object with a unique filename.
    """
    if not image:
        return None

    extension = Path(image.name).suffix
    filename = f'{uuid.uuid4()}{extension}'
    file = ContentFile(image.read(), filename)
    return file
