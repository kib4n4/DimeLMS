from django import forms
from django.db import transaction

from .models import NewsAndEvents, Session, Semester, SEMESTER


# news and events
class NewsAndEventsForm(forms.ModelForm):
    event_time = forms.DateTimeField(
        required=False,
        label="Event/news date & time",
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local", "class": "form-control"},
            format="%Y-%m-%dT%H:%M",
        ),
        help_text="Optional — when this event/news item takes place.",
    )

    class Meta:
        model = NewsAndEvents
        fields = (
            "title",
            "summary",
            "posted_as",
            "image",
            "event_time",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].widget.attrs.update({"class": "form-control"})
        self.fields["summary"].widget.attrs.update({"class": "form-control"})
        self.fields["posted_as"].widget.attrs.update({"class": "form-control"})
        self.fields["image"].widget.attrs.update({"class": "form-control"})
        # HTML5 datetime-local inputs need this exact format to pre-fill
        # correctly when editing an existing post.
        if self.instance and self.instance.pk and self.instance.event_time:
            self.initial["event_time"] = self.instance.event_time.strftime("%Y-%m-%dT%H:%M")


class SessionForm(forms.ModelForm):
    next_session_begins = forms.DateTimeField(
        widget=forms.TextInput(
            attrs={
                "type": "date",
            }
        ),
        required=True,
    )

    class Meta:
        model = Session
        fields = ["session", "is_current_session", "next_session_begins"]


class SemesterForm(forms.ModelForm):
    semester = forms.CharField(
        widget=forms.Select(
            choices=SEMESTER,
            attrs={
                "class": "browser-default custom-select",
            },
        ),
        label="semester",
    )
    is_current_semester = forms.CharField(
        widget=forms.Select(
            choices=((True, "Yes"), (False, "No")),
            attrs={
                "class": "browser-default custom-select",
            },
        ),
        label="is current semester ?",
    )
    session = forms.ModelChoiceField(
        queryset=Session.objects.all(),
        widget=forms.Select(
            attrs={
                "class": "browser-default custom-select",
            }
        ),
        required=True,
    )

    next_semester_begins = forms.DateTimeField(
        widget=forms.TextInput(
            attrs={
                "type": "date",
                "class": "form-control",
            }
        ),
        required=True,
    )

    class Meta:
        model = Semester
        fields = ["semester", "is_current_semester", "session", "next_semester_begins"]
