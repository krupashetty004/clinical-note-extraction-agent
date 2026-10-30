from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0014_knowledge_retrieval_trace"),
    ]

    operations = [
        migrations.AddField(
            model_name="aiconfiguration",
            name="tested_fingerprint",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
    ]
