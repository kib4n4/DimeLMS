import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Makes Program.institution required, now that core.0007 has backfilled
    every existing Program onto the Default Institution — depend on that
    migration directly so this can never run against un-backfilled rows.
    """

    dependencies = [
        ("course", "0009_program_institution_alter_program_title_and_more"),
        ("core", "0007_backfill_default_institution"),
    ]

    operations = [
        migrations.AlterField(
            model_name="program",
            name="institution",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="programs",
                to="core.institution",
            ),
        ),
    ]
