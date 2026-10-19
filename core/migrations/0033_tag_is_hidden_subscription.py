from django.db import migrations, models


def create_subscription_tag(apps, schema_editor):
    Tag = apps.get_model("core", "Tag")
    tag, _ = Tag.objects.get_or_create(name="system:subscription", owner=None)
    tag.is_hidden = True
    tag.save(update_fields=["is_hidden"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0032_merge_20261015_1524"),
    ]

    operations = [
        # An early version of this change (never merged) added the same column
        # under another migration's name, so a development database may have it
        # already: add it only where it is missing
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    "ALTER TABLE core_tag ADD COLUMN IF NOT EXISTS is_hidden boolean NOT NULL DEFAULT false;",
                    reverse_sql="ALTER TABLE core_tag DROP COLUMN IF EXISTS is_hidden;",
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="tag",
                    name="is_hidden",
                    field=models.BooleanField(default=False),
                ),
            ],
        ),
        # The tag is not removed on reverse: line items may be marked with it
        migrations.RunPython(create_subscription_tag, migrations.RunPython.noop),
    ]
