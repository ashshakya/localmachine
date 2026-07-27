from django.db import migrations, models


def create_default_visibility(apps, schema_editor):
    PageVisibility = apps.get_model("workspace", "PageVisibility")
    PageVisibility.objects.get_or_create(pk=1)


class Migration(migrations.Migration):
    dependencies = [("workspace", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="PageVisibility",
            fields=[
                (
                    "id",
                    models.PositiveSmallIntegerField(
                        default=1,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "command_center_enabled",
                    models.BooleanField(
                        default=True,
                        help_text=(
                            "Show the Command Center and allow access to its pages and APIs."
                        ),
                    ),
                ),
                (
                    "api_mocker_enabled",
                    models.BooleanField(
                        default=True,
                        help_text=(
                            "Show the API Mocker and allow access to its management pages and APIs."
                        ),
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "page visibility",
                "verbose_name_plural": "page visibility",
            },
        ),
        migrations.RunPython(
            create_default_visibility,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
