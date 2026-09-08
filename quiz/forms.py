from django import forms
from django.forms.widgets import RadioSelect, Textarea
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.utils.translation import gettext_lazy as _
from django.db import transaction

from django.forms.models import inlineformset_factory

from accounts.models import User
from .models import Question, Quiz, MCQuestion, Choice, CATEGORY_OPTIONS


class QuestionForm(forms.Form):
    def __init__(self, question, *args, **kwargs):
        super(QuestionForm, self).__init__(*args, **kwargs)
        choice_list = [x for x in question.get_choices_list()]
        self.fields["answers"] = forms.ChoiceField(
            choices=choice_list, widget=RadioSelect
        )


class EssayForm(forms.Form):
    def __init__(self, question, *args, **kwargs):
        super(EssayForm, self).__init__(*args, **kwargs)
        self.fields["answers"] = forms.CharField(
            widget=Textarea(attrs={"style": "width:100%"})
        )


class QuizAddForm(forms.ModelForm):
    class Meta:
        model = Quiz
        exclude = []

    questions = forms.ModelMultipleChoiceField(
        queryset=Question.objects.all().select_subclasses(),
        required=False,
        label=_("Questions"),
        widget=FilteredSelectMultiple(verbose_name=_("Questions"), is_stacked=False),
    )

    def __init__(self, *args, **kwargs):
        super(QuizAddForm, self).__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields[
                "questions"
            ].initial = self.instance.question_set.all().select_subclasses()

    def save(self, commit=True):
        quiz = super(QuizAddForm, self).save(commit=False)
        quiz.save()
        quiz.question_set.set(self.cleaned_data["questions"])
        self.save_m2m()
        return quiz


class MCQuestionForm(forms.ModelForm):
    class Meta:
        model = MCQuestion
        exclude = ()

class MCQuestionFormSet(forms.BaseInlineFormSet):
    def clean(self):
        """
        Custom validation for the formset to ensure:
        1. At least two choices are provided and not marked for deletion.
        2. At least one of the choices is marked as correct.
        """
        super().clean()

        # Collect non-deleted forms
        valid_forms = [form for form in self.forms if not form.cleaned_data.get('DELETE', True)]

        valid_choices = ['choice' in form.cleaned_data.keys() for form in valid_forms]
        if(not all(valid_choices)):
            raise forms.ValidationError("You must add a valid choice name.")

        # If all forms are deleted, raise a validation error
        if len(valid_forms) < 2:
            raise forms.ValidationError("You must provide at least two choices.")

        # Check if at least one of the valid forms is marked as correct
        correct_choices = [form.cleaned_data.get('correct', False) for form in valid_forms]

        if not any(correct_choices):
            raise forms.ValidationError("One choice must be marked as correct.")
        
        if correct_choices.count(True)>1:
            raise forms.ValidationError("Only one choice must be marked as correct.")


MCQuestionFormSet = inlineformset_factory(
    MCQuestion,
    Choice,
    form=MCQuestionForm,
    formset=MCQuestionFormSet,
    fields=["choice", "correct"],
    can_delete=True,
    extra=5,
)


class QuizImportForm(forms.Form):
    """Import quiz questions from an uploaded .docx/.pdf document, or a
    direct link to one — see quiz.utils.parse_quiz_document for the
    expected text pattern. Either adds to an existing quiz for the course
    or creates a new one from the fields below."""

    NEW_QUIZ = "__new__"

    quiz = forms.ChoiceField(label=_("Add questions to"))
    new_quiz_title = forms.CharField(
        max_length=60, required=False, label=_("New quiz title")
    )
    new_quiz_description = forms.CharField(
        required=False, widget=forms.Textarea(attrs={"rows": 2}), label=_("Description")
    )
    new_quiz_category = forms.ChoiceField(
        choices=[("", "---------")] + list(CATEGORY_OPTIONS),
        required=False,
        label=_("Category"),
    )
    new_quiz_pass_mark = forms.IntegerField(
        required=False, min_value=0, max_value=100, initial=50, label=_("Pass mark (%)")
    )

    document = forms.FileField(required=False, label=_("Document (.docx or .pdf)"))
    document_url = forms.URLField(
        required=False, label=_("Document link"),
        widget=forms.URLInput(attrs={"placeholder": "https://example.com/quiz.docx"}),
    )

    def __init__(self, *args, course=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.course = course
        choices = [(self.NEW_QUIZ, _("Create a new quiz"))]
        if course is not None:
            choices += [(quiz.pk, quiz.title) for quiz in Quiz.objects.filter(course=course)]
        self.fields["quiz"].choices = choices
        for field in self.fields.values():
            existing = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = (existing + " form-control").strip()

    def clean(self):
        cleaned_data = super().clean()
        document = cleaned_data.get("document")
        document_url = cleaned_data.get("document_url")

        if bool(document) == bool(document_url):
            raise forms.ValidationError(
                _("Provide either a document or a link to one — not both, not neither.")
            )

        if cleaned_data.get("quiz") == self.NEW_QUIZ and not cleaned_data.get(
            "new_quiz_title"
        ):
            self.add_error("new_quiz_title", _("Title is required for a new quiz."))

        return cleaned_data
