from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0009_aiconfiguration"),
    ]

    operations = [
        migrations.AddField(
            model_name="aiconfiguration",
            name="api_key_encrypted",
            field=models.TextField(blank=True, default=""),
        ),
    ]
