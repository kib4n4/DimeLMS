from django.db import migrations, models


DEFAULT_INSTITUTION_NAME = "Default Institution"


def backfill_default_institution(apps, schema_editor):
    Institution = apps.get_model("core", "Institution")
    Program = apps.get_model("course", "Program")
    User = apps.get_model("accounts", "User")

    is_org_member = models.Q(is_org_admin=True) | models.Q(is_lecturer=True) | models.Q(
        is_student=True
    )
    needs_program_backfill = Program.objects.filter(institution__isnull=True).exists()
    needs_user_backfill = User.objects.filter(institution__isnull=True).filter(
        is_org_member
    ).exists()
    if not needs_program_backfill and not needs_user_backfill:
        return

    institution, _created = Institution.objects.get_or_create(
        name=DEFAULT_INSTITUTION_NAME, defaults={"slug": "default-institution"}
    )

    Program.objects.filter(institution__isnull=True).update(institution=institution)
    User.objects.filter(institution__isnull=True).filter(is_org_member).update(
        institution=institution
    )


def unbackfill_default_institution(apps, schema_editor):
    # Reversible as a no-op: we can't tell a backfilled record apart from
    # one an admin has since deliberately assigned to the Default
    # Institution, so reversing just leaves everything as-is rather than
    # guessing which rows to clear.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0006_institution"),
        ("course", "0009_program_institution_alter_program_title_and_more"),
        ("accounts", "0004_user_institution"),
    ]

    operations = [
        migrations.RunPython(
            backfill_default_institution, unbackfill_default_institution
        ),
    ]
