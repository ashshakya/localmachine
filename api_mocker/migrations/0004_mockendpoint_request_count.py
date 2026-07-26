from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("api_mocker", "0003_mockrequestlog")]

    operations = [
        migrations.AddField(
            model_name="mockendpoint",
            name="request_count",
            field=models.PositiveBigIntegerField(default=0),
        ),
    ]
