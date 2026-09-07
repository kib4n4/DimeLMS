from django.db import migrations, models
import django.db.models.deletion


def migrate_semester_labels_to_fk(apps, schema_editor):
    """
    Course.semester used to be a plain "First"/"Second"/"Third" label. Map
    each course to a real Semester row carrying that label — preferring the
    currently-active session's semester when there's a choice, since that's
    the most likely intended match; otherwise falls back to the first
    matching semester found. Courses whose label matches no Semester at all
    are left unset (semester=None) rather than guessed at, since guessing a
    specific session/year would be pure fabrication — an admin needs to
    assign those manually.
    """
    Course = apps.get_model("course", "Course")
    Semester = apps.get_model("core", "Semester")
    Session = apps.get_model("core", "Session")

    current_session = Session.objects.filter(is_current_session=True).first()
    matched_by_label = {}

    for course in Course.objects.exclude(semester_label__isnull=True).exclude(semester_label=""):
        label = course.semester_label
        if label not in matched_by_label:
            candidates = Semester.objects.filter(semester=label)
            match = None
            if current_session:
                match = candidates.filter(session=current_session).first()
            if match is None:
                match = candidates.order_by("id").first()
            matched_by_label[label] = match

        match = matched_by_label[label]
        if match is not None:
            course.semester_id = match.id
            course.save(update_fields=["semester"])


def restore_semester_labels(apps, schema_editor):
    """
    Reverse of the above: restores the label for every course whose
    semester FK was successfully set. A course that migrate_semester_labels
    _to_fk couldn't match to any Semester (semester left None) has no label
    to recover — that information was genuinely lost, not just moved — so
    it gets an empty label rather than failing the rollback outright.
    """
    Course = apps.get_model("course", "Course")
    for course in Course.objects.all():
        course.semester_label = course.semester.semester if course.semester_id else ""
        course.save(update_fields=["semester_label"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_newsandevents_summary_es_newsandevents_summary_fr_and_more"),
        ("course", "0003_course_summary_es_course_summary_fr_course_title_es_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="course",
            old_name="semester",
            new_name="semester_label",
        ),
        # Gives the (temporary) renamed column a default, purely so that
        # rolling this migration all the way back — which re-adds this
        # column via Django's auto-reverse of the RemoveField below, before
        # RunPython's reverse gets a chance to repopulate real values —
        # doesn't hit a NOT NULL failure on the courses that already exist.
        migrations.AlterField(
            model_name="course",
            name="semester_label",
            field=models.CharField(
                blank=True,
                default="",
                max_length=200,
                choices=[
                    ("First", "First"),
                    ("Second", "Second"),
                    ("Third", "Third"),
                ],
            ),
        ),
        migrations.AddField(
            model_name="course",
            name="semester",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="courses",
                to="core.semester",
            ),
        ),
        migrations.RunPython(
            migrate_semester_labels_to_fk,
            restore_semester_labels,
        ),
        migrations.RemoveField(
            model_name="course",
            name="semester_label",
        ),
    ]
