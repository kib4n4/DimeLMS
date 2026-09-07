from django.db import models
from django.urls import reverse
from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db.models.signals import pre_save, post_save, post_delete
from django.db.models import Q
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _

# project import
from .utils import *
from core.models import ActivityLog

YEARS = (
    (1, "1"),
    (2, "2"),
    (3, "3"),
    (4, "4"),
    (4, "5"),
    (4, "6"),
)

# LEVEL_COURSE = "Level course"
BACHELOR_DEGREE = _("Bachelor")
MASTER_DEGREE = _("Master")

LEVEL = (
    # (LEVEL_COURSE, "Level course"),
    (BACHELOR_DEGREE, _("Bachelor Degree")),
    (MASTER_DEGREE, _("Master Degree")),
)

FIRST = _("First")
SECOND = _("Second")
THIRD = _("Third")

SEMESTER = (
    (FIRST, _("First")),
    (SECOND, _("Second")),
    (THIRD, _("Third")),
)

# A course's length_type picks the recommended per-module duration band
# shown as guidance on the module form — it isn't hard-enforced, a
# facilitator can still save a module outside the range.
LONG_COURSE = "long"
SHORT_COURSE = "short"

COURSE_LENGTH = (
    (LONG_COURSE, _("Long course (modules ~2h–2h30m)")),
    (SHORT_COURSE, _("Short course (modules ~45m–1h)")),
)

# (min minutes, max minutes) recommended band per length_type.
MODULE_DURATION_RANGE = {
    LONG_COURSE: (120, 150),
    SHORT_COURSE: (45, 60),
}


class ProgramManager(models.Manager):
    def search(self, query=None):
        queryset = self.get_queryset()
        if query is not None:
            or_lookup = Q(title__icontains=query) | Q(summary__icontains=query)
            queryset = queryset.filter(
                or_lookup
            ).distinct()  # distinct() is often necessary with Q lookups
        return queryset


class Program(models.Model):
    title = models.CharField(max_length=150, unique=True)
    summary = models.TextField(null=True, blank=True)

    objects = ProgramManager()

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("program_detail", kwargs={"pk": self.pk})


@receiver(post_save, sender=Program)
def log_save(sender, instance, created, **kwargs):
    verb = "created" if created else "updated"
    ActivityLog.objects.create(message=_(f"The program '{instance}' has been {verb}."))


@receiver(post_delete, sender=Program)
def log_delete(sender, instance, **kwargs):
    ActivityLog.objects.create(message=_(f"The program '{instance}' has been deleted."))


class CourseManager(models.Manager):
    def search(self, query=None):
        queryset = self.get_queryset()
        if query is not None:
            or_lookup = (
                Q(title__icontains=query)
                | Q(summary__icontains=query)
                | Q(code__icontains=query)
                | Q(slug__icontains=query)
            )
            queryset = queryset.filter(
                or_lookup
            ).distinct()  # distinct() is often necessary with Q lookups
        return queryset


class Course(models.Model):
    slug = models.SlugField(blank=True, unique=True)
    title = models.CharField(max_length=200, null=True)
    code = models.CharField(max_length=200, unique=True, null=True)
    credit = models.IntegerField(null=True, default=0)
    summary = models.TextField(max_length=200, blank=True, null=True)
    program = models.ForeignKey(Program, on_delete=models.CASCADE)
    level = models.CharField(max_length=25, choices=LEVEL, null=True)
    year = models.IntegerField(choices=YEARS, default=0)
    semester = models.ForeignKey(
        "core.Semester",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="courses",
    )
    is_elective = models.BooleanField(default=False, blank=True, null=True)
    length_type = models.CharField(
        max_length=10,
        choices=COURSE_LENGTH,
        default=LONG_COURSE,
        help_text=_(
            "Picks the recommended per-module duration shown when adding a "
            "module to this course."
        ),
    )

    objects = CourseManager()

    def __str__(self):
        return "{0} ({1})".format(self.title, self.code)

    def get_absolute_url(self):
        return reverse("course_detail", kwargs={"slug": self.slug})

    @property
    def is_current_semester(self):
        return bool(self.semester_id and self.semester.is_current_semester)

    @property
    def recommended_module_duration(self):
        """(min minutes, max minutes) guidance band for this course's length_type."""
        return MODULE_DURATION_RANGE.get(self.length_type, MODULE_DURATION_RANGE[LONG_COURSE])

    def progress_for_student(self, student):
        """
        Weighted-average completion percentage (0-100, int) across this
        course's modules for `student` — each module's share of the total
        is proportional to its target duration. A course with no modules
        (or none with a duration) returns None rather than 0, so templates
        can distinguish "nothing to track yet" from "0% complete".
        """
        modules = list(self.modules.all())
        total_duration = sum(m.duration_minutes for m in modules)
        if not total_duration:
            return None
        progress_by_module = {
            p.module_id: p
            for p in ModuleProgress.objects.filter(
                student=student, module__course=self
            )
        }
        covered = 0
        for module in modules:
            progress = progress_by_module.get(module.id)
            percent = progress.percent_covered if progress else 0
            covered += percent * module.duration_minutes
        return round(covered / total_duration)


def course_pre_save_receiver(sender, instance, *args, **kwargs):
    if not instance.slug:
        instance.slug = unique_slug_generator(instance)


pre_save.connect(course_pre_save_receiver, sender=Course)


@receiver(post_save, sender=Course)
def log_save(sender, instance, created, **kwargs):
    verb = "created" if created else "updated"
    ActivityLog.objects.create(message=_(f"The course '{instance}' has been {verb}."))


@receiver(post_delete, sender=Course)
def log_delete(sender, instance, **kwargs):
    ActivityLog.objects.create(message=_(f"The course '{instance}' has been deleted."))


class CourseAllocation(models.Model):
    lecturer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name=_("allocated_lecturer"),
    )
    courses = models.ManyToManyField(Course, related_name=_("allocated_course"))
    session = models.ForeignKey(
        "core.Session", on_delete=models.CASCADE, blank=True, null=True
    )

    def __str__(self):
        return self.lecturer.get_full_name

    def get_absolute_url(self):
        return reverse("edit_allocated_course", kwargs={"pk": self.pk})


class Module(models.Model):
    """
    A titled, ordered lesson within a course — the unit course/module
    tracking is measured against. Files, videos and YouTube links are
    optionally grouped under a module via their own `module` field; a
    module's `duration_minutes` is the target a student's tracked time
    (see ModuleProgress) is measured against.
    """

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="modules")
    title = models.CharField(max_length=200)
    slug = models.SlugField(blank=True, unique=True)
    summary = models.TextField(blank=True, null=True)
    order = models.PositiveIntegerField(default=0)
    duration_minutes = models.PositiveIntegerField(
        help_text=_("Target duration for this module, in minutes.")
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.title} ({self.course})"

    def get_absolute_url(self):
        return reverse(
            "module_detail", kwargs={"slug": self.course.slug, "pk": self.pk}
        )

    @property
    def duration_seconds(self):
        return self.duration_minutes * 60

    def progress_for_student(self, student):
        return ModuleProgress.objects.filter(student=student, module=self).first()


def module_pre_save_receiver(sender, instance, *args, **kwargs):
    if not instance.slug:
        instance.slug = unique_slug_generator(instance)


pre_save.connect(module_pre_save_receiver, sender=Module)


@receiver(post_save, sender=Module)
def log_save(sender, instance, created, **kwargs):
    verb = "created" if created else "updated"
    ActivityLog.objects.create(
        message=_(f"The module '{instance.title}' of '{instance.course}' has been {verb}.")
    )


@receiver(post_delete, sender=Module)
def log_delete(sender, instance, **kwargs):
    ActivityLog.objects.create(
        message=_(f"The module '{instance.title}' of '{instance.course}' has been deleted.")
    )


class Upload(models.Model):
    title = models.CharField(max_length=100)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    module = models.ForeignKey(
        Module, on_delete=models.SET_NULL, null=True, blank=True, related_name="uploads"
    )
    file = models.FileField(
        upload_to="course_files/",
        help_text="Valid Files: pdf, docx, doc, xls, xlsx, ppt, pptx, zip, rar, 7zip",
        validators=[
            FileExtensionValidator(
                [
                    "pdf",
                    "docx",
                    "doc",
                    "xls",
                    "xlsx",
                    "ppt",
                    "pptx",
                    "zip",
                    "rar",
                    "7zip",
                ]
            )
        ],
    )
    updated_date = models.DateTimeField(auto_now=True, auto_now_add=False, null=True)
    upload_time = models.DateTimeField(auto_now=False, auto_now_add=True, null=True)

    def __str__(self):
        return str(self.file)[6:]

    def get_extension_short(self):
        ext = str(self.file).split(".")
        ext = ext[len(ext) - 1]

        if ext in ("doc", "docx"):
            return "word"
        elif ext == "pdf":
            return "pdf"
        elif ext in ("xls", "xlsx"):
            return "excel"
        elif ext in ("ppt", "pptx"):
            return "powerpoint"
        elif ext in ("zip", "rar", "7zip"):
            return "archive"

    def delete(self, *args, **kwargs):
        self.file.delete()
        super().delete(*args, **kwargs)


@receiver(post_save, sender=Upload)
def log_save(sender, instance, created, **kwargs):
    if created:
        ActivityLog.objects.create(
            message=_(
                f"The file '{instance.title}' has been uploaded to the course '{instance.course}'."
            )
        )
    else:
        ActivityLog.objects.create(
            message=_(
                f"The file '{instance.title}' of the course '{instance.course}' has been updated."
            )
        )


@receiver(post_delete, sender=Upload)
def log_delete(sender, instance, **kwargs):
    ActivityLog.objects.create(
        message=_(
            f"The file '{instance.title}' of the course '{instance.course}' has been deleted."
        )
    )


class UploadVideo(models.Model):
    title = models.CharField(max_length=100)
    slug = models.SlugField(blank=True, unique=True)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    module = models.ForeignKey(
        Module, on_delete=models.SET_NULL, null=True, blank=True, related_name="videos"
    )
    video = models.FileField(
        upload_to="course_videos/",
        help_text=_("Valid video formats: mp4, mkv, wmv, 3gp, f4v, avi, mp3"),
        validators=[
            FileExtensionValidator(["mp4", "mkv", "wmv", "3gp", "f4v", "avi", "mp3"])
        ],
    )
    summary = models.TextField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now=False, auto_now_add=True, null=True)

    def __str__(self):
        return str(self.title)

    def get_absolute_url(self):
        return reverse(
            "video_single", kwargs={"slug": self.course.slug, "video_slug": self.slug}
        )

    def delete(self, *args, **kwargs):
        self.video.delete()
        super().delete(*args, **kwargs)


def video_pre_save_receiver(sender, instance, *args, **kwargs):
    if not instance.slug:
        instance.slug = unique_slug_generator(instance)


pre_save.connect(video_pre_save_receiver, sender=UploadVideo)


@receiver(post_save, sender=UploadVideo)
def log_save(sender, instance, created, **kwargs):
    if created:
        ActivityLog.objects.create(
            message=_(
                f"The video '{instance.title}' has been uploaded to the course {instance.course}."
            )
        )
    else:
        ActivityLog.objects.create(
            message=_(
                f"The video '{instance.title}' of the course '{instance.course}' has been updated."
            )
        )


@receiver(post_delete, sender=UploadVideo)
def log_delete(sender, instance, **kwargs):
    ActivityLog.objects.create(
        message=_(
            f"The video '{instance.title}' of the course '{instance.course}' has been deleted."
        )
    )


class CourseLink(models.Model):
    """A YouTube video shared as course material, alongside file
    Uploads and self-hosted UploadVideos — no file storage of our own,
    just a validated link plus the embeddable player."""

    title = models.CharField(max_length=100)
    slug = models.SlugField(blank=True, unique=True)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    module = models.ForeignKey(
        Module, on_delete=models.SET_NULL, null=True, blank=True, related_name="links"
    )
    url = models.URLField(
        help_text=_(
            "A YouTube link, e.g. https://www.youtube.com/watch?v=... or https://youtu.be/..."
        ),
        validators=[validate_youtube_url],
    )
    summary = models.TextField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now=False, auto_now_add=True, null=True)

    def __str__(self):
        return str(self.title)

    @property
    def youtube_id(self):
        return extract_youtube_id(self.url)

    @property
    def embed_url(self):
        video_id = self.youtube_id
        return f"https://www.youtube-nocookie.com/embed/{video_id}" if video_id else None

    @property
    def thumbnail_url(self):
        video_id = self.youtube_id
        return f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg" if video_id else None

    def get_absolute_url(self):
        return reverse(
            "link_single", kwargs={"slug": self.course.slug, "link_slug": self.slug}
        )


def link_pre_save_receiver(sender, instance, *args, **kwargs):
    if not instance.slug:
        instance.slug = unique_slug_generator(instance)


pre_save.connect(link_pre_save_receiver, sender=CourseLink)


@receiver(post_save, sender=CourseLink)
def log_save(sender, instance, created, **kwargs):
    if created:
        ActivityLog.objects.create(
            message=_(
                f"The link '{instance.title}' has been added to the course {instance.course}."
            )
        )
    else:
        ActivityLog.objects.create(
            message=_(
                f"The link '{instance.title}' of the course '{instance.course}' has been updated."
            )
        )


@receiver(post_delete, sender=CourseLink)
def log_delete(sender, instance, **kwargs):
    ActivityLog.objects.create(
        message=_(
            f"The link '{instance.title}' of the course '{instance.course}' has been deleted."
        )
    )


class ModuleProgress(models.Model):
    """
    One student's tracked time on one module. `seconds_covered` accumulates
    from the browser-side tracker (real video playback time for videos,
    time-on-page for documents/links — see record_module_progress) and is
    capped at the module's target duration; `percent_covered` and
    `completed` are derived from that against `module.duration_seconds`.
    """

    student = models.ForeignKey(
        "accounts.Student", on_delete=models.CASCADE, related_name="module_progress"
    )
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="progress")
    seconds_covered = models.PositiveIntegerField(default=0)
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_activity = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("student", "module")
        verbose_name_plural = "Module progress"

    def __str__(self):
        return f"{self.student} — {self.module} ({self.percent_covered}%)"

    @property
    def percent_covered(self):
        target = self.module.duration_seconds
        if not target:
            return 0
        return round(min(self.seconds_covered, target) / target * 100)


class CourseOffer(models.Model):
    _("""NOTE: Only department head can offer semester courses""")

    dep_head = models.ForeignKey("accounts.DepartmentHead", on_delete=models.CASCADE)

    def __str__(self):
        return "{}".format(self.dep_head)
