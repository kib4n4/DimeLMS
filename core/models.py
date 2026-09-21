import random
import string

from django.db import models
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.urls import reverse
from django.core.validators import FileExtensionValidator
from django.contrib.auth.models import AbstractUser
from django.db.models import Q
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _


NEWS = "News"
EVENTS = "Event"

POST = (
    (NEWS, _("News")),
    (EVENTS, _("Event")),
)

FIRST = "First"
SECOND = "Second"
THIRD = "Third"

SEMESTER = (
    (FIRST, _("First")),
    (SECOND, _("Second")),
    (THIRD, _("Third")),
)


class Institution(models.Model):
    """
    A tenant / organization boundary. Every Program belongs to exactly one
    Institution (and every Course, through its Program); every non-super
    User (org admin, facilitator, student) belongs to exactly one
    Institution too. A superuser has no institution and sees across all
    of them — everyone else's queries are scoped to their own.
    """

    name = models.CharField(max_length=200, unique=True)
    # Short unique identifier for the organization, e.g. "DIME001". Nullable
    # at the DB level so existing rows migrate cleanly (a data migration
    # backfills them); required in the form for anything created since.
    code = models.CharField(max_length=20, unique=True, null=True, blank=True)
    email = models.EmailField(_("contact email"), blank=True)
    phone = models.CharField(_("contact phone"), max_length=30, blank=True)
    contact_name = models.CharField(_("contact person"), max_length=100, blank=True)
    slug = models.SlugField(blank=True, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("institution_edit", kwargs={"pk": self.pk})


def _unique_institution_slug(instance):
    base_slug = slugify(instance.name)
    slug = base_slug
    while Institution.objects.filter(slug=slug).exclude(pk=instance.pk).exists():
        suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
        slug = f"{base_slug}-{suffix}"
    return slug


@receiver(pre_save, sender=Institution)
def institution_pre_save_receiver(sender, instance, *args, **kwargs):
    if not instance.slug:
        instance.slug = _unique_institution_slug(instance)


class NewsAndEventsQuerySet(models.query.QuerySet):
    def search(self, query):
        lookups = (
            Q(title__icontains=query)
            | Q(summary__icontains=query)
            | Q(posted_as__icontains=query)
        )
        return self.filter(lookups).distinct()


class NewsAndEventsManager(models.Manager):
    def get_queryset(self):
        return NewsAndEventsQuerySet(self.model, using=self._db)

    def all(self):
        return self.get_queryset()

    def get_by_id(self, id):
        qs = self.get_queryset().filter(
            id=id
        )  # NewsAndEvents.objects == self.get_queryset()
        if qs.count() == 1:
            return qs.first()
        return None

    def search(self, query):
        return self.get_queryset().search(query)


class NewsAndEvents(models.Model):
    title = models.CharField(max_length=200, null=True)
    summary = models.TextField(max_length=200, blank=True, null=True)
    posted_as = models.CharField(choices=POST, max_length=10)
    image = models.ImageField(
        upload_to="news_events/",
        blank=True,
        null=True,
        help_text=_("Optional image shown on the card."),
    )
    event_time = models.DateTimeField(
        blank=True,
        null=True,
        help_text=_(
            "When the event/news item takes place — shown on the card if set."
        ),
    )
    updated_date = models.DateTimeField(auto_now=True, auto_now_add=False, null=True)
    upload_time = models.DateTimeField(auto_now=False, auto_now_add=True, null=True)

    objects = NewsAndEventsManager()

    def __str__(self):
        return self.title

    def delete(self, *args, **kwargs):
        if self.image:
            self.image.delete(save=False)
        super().delete(*args, **kwargs)


class Session(models.Model):
    session = models.CharField(max_length=200, unique=True)
    is_current_session = models.BooleanField(default=False, blank=True, null=True)
    next_session_begins = models.DateField(blank=True, null=True)

    def __str__(self):
        return self.session


class Semester(models.Model):
    semester = models.CharField(max_length=10, choices=SEMESTER, blank=True)
    is_current_semester = models.BooleanField(default=False, blank=True, null=True)
    session = models.ForeignKey(
        Session, on_delete=models.CASCADE, blank=True, null=True
    )
    next_semester_begins = models.DateField(null=True, blank=True)

    def __str__(self):
        return self.semester


class ActivityLog(models.Model):
    message = models.TextField()
    created_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"[{self.created_at}]{self.message}"


class SiteConfiguration(models.Model):
    """A single row of site-wide toggles, managed from the Admin Panel.
    Use SiteConfiguration.get_solo() rather than querying directly."""

    course_registration_open = models.BooleanField(
        default=True,
        help_text=_("When off, students can't add or drop courses themselves."),
    )
    read_aloud_voice_name = models.CharField(
        max_length=150,
        blank=True,
        help_text=_(
            "The exact browser voice name (from the Admin Panel's voice picker) "
            "to prefer for the module read-aloud feature. Voices are local to "
            "each visitor's browser, so this is only used if that visitor's "
            "browser happens to have a voice with this exact name — otherwise "
            "read_aloud_voice_lang is used as a fallback."
        ),
    )
    read_aloud_voice_lang = models.CharField(
        max_length=20,
        blank=True,
        help_text=_(
            "BCP-47 language tag (e.g. 'en-US') of the preferred read-aloud "
            "voice, used as a fallback when a visitor's browser doesn't have "
            "the exact voice named above — any voice in this language is used "
            "instead of the browser's own default."
        ),
    )

    class Meta:
        verbose_name = "Site configuration"
        verbose_name_plural = "Site configuration"

    def __str__(self):
        return "Site configuration"

    @classmethod
    def get_solo(cls):
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj
