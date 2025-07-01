import uuid
from pathlib import Path

from django.core.files.base import ContentFile
from PIL import Image


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


def validate_image_dimensions(image, required_width=512, required_height=512):
    """
    Validate that an image has the required dimensions.

    Args:
        image: The image file to validate
        required_width: The required width in pixels (default: 512)
        required_height: The required height in pixels (default: 512)

    Returns:
        tuple: (is_valid, error_message)
    """
    try:
        img = Image.open(image)
        width, height = img.size

        if width != required_width or height != required_height:
            return False, f'Image must be exactly {required_width}x{required_height} pixels. Got {width}x{height}.'

        return True, None
    except Exception as e:
        return False, f'Invalid image file: {str(e)}'


def validate_image_max_dimensions(image, max_width=1920, max_height=1080):
    """
    Validate that an image does not exceed maximum dimensions.

    Args:
        image: The image file to validate
        max_width: The maximum width in pixels (default: 1920)
        max_height: The maximum height in pixels (default: 1080)

    Returns:
        tuple: (is_valid, error_message)
    """
    try:
        img = Image.open(image)
        width, height = img.size

        if width > max_width or height > max_height:
            return False, f'Image dimensions must not exceed {max_width}x{max_height} pixels. Got {width}x{height}.'

        return True, None
    except Exception as e:
        return False, f'Invalid image file: {str(e)}'
