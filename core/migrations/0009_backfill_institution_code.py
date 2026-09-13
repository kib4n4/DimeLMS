import re

from django.db import migrations


def _slug_prefix(name):
    letters = re.sub(r"[^A-Za-z]", "", name).upper()
    return (letters[:4] or "ORG")


def backfill_institution_code(apps, schema_editor):
    """Give every existing institution a code derived from its name, e.g.
    "Dime Consultants Limited" -> "DIME001". New institutions get one from
    the form; this is only for rows that predate the field."""
    Institution = apps.get_model("core", "Institution")
    taken = set(
        Institution.objects.exclude(code__isnull=True)
        .exclude(code="")
        .values_list("code", flat=True)
    )
    for institution in Institution.objects.filter(code__isnull=True).order_by("pk"):
        prefix = _slug_prefix(institution.name)
        n = 1
        code = f"{prefix}{n:03d}"
        while code in taken:
            n += 1
            code = f"{prefix}{n:03d}"
        institution.code = code
        institution.save(update_fields=["code"])
        taken.add(code)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0008_institution_code_institution_contact_name_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_institution_code, noop),
    ]
