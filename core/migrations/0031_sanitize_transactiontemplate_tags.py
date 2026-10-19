from django.db import migrations


def remove_foreign_template_tags(apps, schema_editor):
    TransactionTemplate = apps.get_model("core", "TransactionTemplate")
    database = schema_editor.connection.alias

    for template in TransactionTemplate.objects.using(database).iterator():
        foreign_tag_ids = [
            tag.pk
            for tag in template.tags.all()
            if tag.owner_id is not None and tag.owner_id != template.user_id
        ]
        if foreign_tag_ids:
            template.tags.remove(*foreign_tag_ids)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0030_remove_transactiontemplate_tag_and_more"),
    ]

    operations = [
        migrations.RunPython(
            remove_foreign_template_tags,
            migrations.RunPython.noop,
        ),
    ]