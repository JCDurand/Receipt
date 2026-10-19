from django.db import migrations

PREDEFINED_TAGS = [
    "Groceries",
    "Fuel",
    "Salary",
    "Woolworths",
    "Checkers",
    "Pick n Pay",
    "Spar",
]


def seed_and_copy(apps, schema_editor):
    Tag = apps.get_model("core", "Tag")
    Item = apps.get_model("core", "Item")

    # Any tag which exists already predates ownership, so it is shared and
    # becomes predefined along with these
    for name in PREDEFINED_TAGS:
        Tag.objects.get_or_create(name=name, owner=None)

    # An item had one tag; it now has a set of them
    for item in Item.objects.exclude(tag=None):
        item.tags.add(item.tag)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0017_tag_owner_item_tags"),
    ]

    operations = [
        # Predefined tags are not removed on reverse: items may be tagged with them
        migrations.RunPython(seed_and_copy, migrations.RunPython.noop),
    ]
