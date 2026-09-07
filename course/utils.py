import datetime
import os
import random
import re
import string

from django.core.exceptions import ValidationError
from django.utils.text import slugify

YOUTUBE_URL_PATTERN = re.compile(
    r"(?:youtube\.com/(?:watch\?v=|embed/|v/|shorts/)|youtu\.be/)([A-Za-z0-9_-]{11})"
)


def extract_youtube_id(url):
    """Pull the 11-char video id out of any common YouTube URL shape
    (watch?v=, youtu.be/, embed/, shorts/), or None if it doesn't match."""
    if not url:
        return None
    match = YOUTUBE_URL_PATTERN.search(url)
    return match.group(1) if match else None


def validate_youtube_url(value):
    if not extract_youtube_id(value):
        raise ValidationError(
            "Enter a valid YouTube link, e.g. https://www.youtube.com/watch?v=... or https://youtu.be/..."
        )


def random_string_generator(size=10, chars=string.ascii_lowercase + string.digits):
    return "".join(random.choice(chars) for _ in range(size))


def unique_slug_generator(instance, new_slug=None):
    """
    This is for a Django project and it assumes your instance
    has a model with a slug field and a title character (char) field.
    """
    if new_slug is not None:
        slug = new_slug
    else:
        slug = slugify(instance.title)

    Klass = instance.__class__
    qs_exists = Klass.objects.filter(slug=slug).exists()
    if qs_exists:
        new_slug = "{slug}-{randstr}".format(
            slug=slug, randstr=random_string_generator(size=4)
        )
        return unique_slug_generator(instance, new_slug=new_slug)
    return slug
