"""Bounded, normalized tournament artwork stored through Django's image field."""

from io import BytesIO
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_COVER_BYTES = 10 * 1024 * 1024
MAX_COVER_PIXELS = 25_000_000
MAX_COVER_EDGE = 1600
COVER_FORMATS = {'JPEG', 'PNG', 'WEBP'}


def validate_cover_image(image):
    if image.size > MAX_COVER_BYTES:
        raise ValidationError('Choose an image no larger than 10 MB.')
    try:
        image.seek(0)
        with Image.open(image) as picture:
            if picture.format not in COVER_FORMATS:
                raise ValidationError('Choose a JPEG, PNG, or WebP image.')
            if picture.width * picture.height > MAX_COVER_PIXELS:
                raise ValidationError('Choose an image with no more than 25 million pixels.')
            picture.verify()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as error:
        raise ValidationError('Choose a valid JPEG, PNG, or WebP image.') from error
    finally:
        image.seek(0)
    return image


def prepare_cover_image(image):
    validate_cover_image(image)
    try:
        with Image.open(image) as source:
            picture = ImageOps.exif_transpose(source)
            picture.thumbnail((MAX_COVER_EDGE, MAX_COVER_EDGE), Image.Resampling.LANCZOS)
            rgba = picture.convert('RGBA')
            background = Image.new('RGB', rgba.size, 'white')
            background.paste(rgba, mask=rgba.getchannel('A'))
            output = BytesIO()
            background.save(output, format='JPEG', quality=85, optimize=True)
    except (OSError, ValueError, Image.DecompressionBombError) as error:
        raise ValidationError('Choose a valid JPEG, PNG, or WebP image.') from error
    finally:
        image.seek(0)
    return ContentFile(output.getvalue(), name=f'{uuid4()}.jpg')
