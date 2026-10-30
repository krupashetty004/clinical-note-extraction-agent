from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0013_alter_aiconfiguration_provider"),
    ]

    operations = [
        migrations.AddField(
            model_name="clinicalprocessingrun",
            name="knowledge_references",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="clinicalprocessingrun",
            name="knowledge_retrieval_status",
            field=models.CharField(
                choices=[
                    ("not_attempted", "Not attempted"),
                    ("no_matches", "No matching references"),
                    ("retrieved", "References retrieved"),
                    ("unavailable", "Retrieval unavailable"),
                ],
                default="not_attempted",
                max_length=20,
            ),
        ),
    ]
