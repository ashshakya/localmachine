import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("tunnels", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="tunnelidentity",
            name="owner",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="tunnel_identities",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="tunnelidentity",
            name="token_ciphertext",
            field=models.TextField(blank=True, editable=False),
        ),
    ]
