from django import forms
from accounts.models import User
from core.models import Semester
from .models import (
    Program,
    Course,
    CourseAllocation,
    Upload,
    UploadVideo,
    CourseLink,
    Module,
)


class ProgramForm(forms.ModelForm):
    class Meta:
        model = Program
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].widget.attrs.update({"class": "form-control"})
        self.fields["summary"].widget.attrs.update({"class": "form-control"})


class SemesterModelChoiceField(forms.ModelChoiceField):
    """Disambiguates same-named semesters across sessions, e.g. "First"
    appears once per session — show "2025/2026 - First", not just "First"."""

    def label_from_instance(self, obj):
        return f"{obj.session} - {obj.get_semester_display()}" if obj.session_id else obj.get_semester_display()


class CourseAddForm(forms.ModelForm):
    semester = SemesterModelChoiceField(
        queryset=Semester.objects.select_related("session").order_by(
            "-session__id", "semester"
        ),
        required=False,
    )

    class Meta:
        model = Course
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].widget.attrs.update({"class": "form-control"})
        self.fields["code"].widget.attrs.update({"class": "form-control"})
        # self.fields['courseUnit'].widget.attrs.update({'class': 'form-control'})
        self.fields["credit"].widget.attrs.update({"class": "form-control"})
        self.fields["summary"].widget.attrs.update({"class": "form-control"})
        self.fields["program"].widget.attrs.update({"class": "form-control"})
        self.fields["level"].widget.attrs.update({"class": "form-control"})
        self.fields["year"].widget.attrs.update({"class": "form-control"})
        self.fields["semester"].widget.attrs.update({"class": "form-control"})
        self.fields["length_type"].widget.attrs.update({"class": "form-control"})


class CourseAllocationForm(forms.ModelForm):
    courses = forms.ModelMultipleChoiceField(
        queryset=Course.objects.all().order_by("level"),
        widget=forms.CheckboxSelectMultiple(
            attrs={"class": "browser-default checkbox"}
        ),
        required=True,
    )
    lecturer = forms.ModelChoiceField(
        queryset=User.objects.filter(is_lecturer=True),
        widget=forms.Select(attrs={"class": "browser-default custom-select"}),
        label="lecturer",
    )

    class Meta:
        model = CourseAllocation
        fields = ["lecturer", "courses"]

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user")
        super(CourseAllocationForm, self).__init__(*args, **kwargs)
        self.fields["lecturer"].queryset = User.objects.filter(is_lecturer=True)


class EditCourseAllocationForm(forms.ModelForm):
    courses = forms.ModelMultipleChoiceField(
        queryset=Course.objects.all().order_by("level"),
        widget=forms.CheckboxSelectMultiple,
        required=True,
    )
    lecturer = forms.ModelChoiceField(
        queryset=User.objects.filter(is_lecturer=True),
        widget=forms.Select(attrs={"class": "browser-default custom-select"}),
        label="lecturer",
    )

    class Meta:
        model = CourseAllocation
        fields = ["lecturer", "courses"]

    def __init__(self, *args, **kwargs):
        #    user = kwargs.pop('user')
        super(EditCourseAllocationForm, self).__init__(*args, **kwargs)
        self.fields["lecturer"].queryset = User.objects.filter(is_lecturer=True)


# Add/edit a module (lesson) within a course
class ModuleForm(forms.ModelForm):
    class Meta:
        model = Module
        fields = ("title", "summary", "order", "duration_minutes")

    def __init__(self, *args, course=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.course = course or getattr(self.instance, "course", None)
        for name in self.fields:
            self.fields[name].widget.attrs.update({"class": "form-control"})
        self.fields["summary"].required = False
        if self.course:
            low, high = self.course.recommended_module_duration
            self.fields["duration_minutes"].help_text = (
                f"Recommended for a {self.course.get_length_type_display()}: "
                f"{low}–{high} minutes. Not enforced — you can save outside this range."
            )

    def clean_duration_minutes(self):
        value = self.cleaned_data["duration_minutes"]
        if value <= 0:
            raise forms.ValidationError("Duration must be greater than 0 minutes.")
        return value


def _module_field_for_course(course):
    """A shared, optional "Module" field for the material-upload forms
    below, scoped to the given course's modules."""
    field = forms.ModelChoiceField(
        queryset=course.modules.all() if course else Module.objects.none(),
        required=False,
        label="Module",
        help_text="Group this under a module so it counts toward the student's tracked progress.",
    )
    field.widget.attrs.update({"class": "form-control"})
    return field


# Upload files to specific course
class UploadFormFile(forms.ModelForm):
    class Meta:
        model = Upload
        fields = (
            "title",
            "file",
            "module",
        )

    def __init__(self, *args, course=None, **kwargs):
        super().__init__(*args, **kwargs)
        course = course or getattr(self.instance, "course", None)
        self.fields["title"].widget.attrs.update({"class": "form-control"})
        self.fields["file"].widget.attrs.update({"class": "form-control"})
        self.fields["module"] = _module_field_for_course(course)


# Upload video to specific course
class UploadFormVideo(forms.ModelForm):
    class Meta:
        model = UploadVideo
        fields = (
            "title",
            "video",
            "module",
        )

    def __init__(self, *args, course=None, **kwargs):
        super().__init__(*args, **kwargs)
        course = course or getattr(self.instance, "course", None)
        self.fields["title"].widget.attrs.update({"class": "form-control"})
        self.fields["video"].widget.attrs.update({"class": "form-control"})
        self.fields["module"] = _module_field_for_course(course)


# Share a YouTube link as material for a specific course
class UploadFormLink(forms.ModelForm):
    class Meta:
        model = CourseLink
        fields = (
            "title",
            "url",
            "summary",
            "module",
        )

    def __init__(self, *args, course=None, **kwargs):
        super().__init__(*args, **kwargs)
        course = course or getattr(self.instance, "course", None)
        self.fields["title"].widget.attrs.update({"class": "form-control"})
        self.fields["url"].widget.attrs.update(
            {
                "class": "form-control",
                "placeholder": "https://www.youtube.com/watch?v=...",
            }
        )
        self.fields["summary"].widget.attrs.update({"class": "form-control"})
        self.fields["summary"].required = False
        self.fields["module"] = _module_field_for_course(course)
