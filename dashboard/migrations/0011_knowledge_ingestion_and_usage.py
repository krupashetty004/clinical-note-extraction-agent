from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0010_aiconfiguration_api_key"),
    ]

    operations = [
        migrations.AddField(
            model_name="knowledgedocument",
            name="ingestion_error",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="knowledgedocument",
            name="ingestion_status",
            field=models.CharField(default="manual", max_length=32),
        ),
        migrations.AddField(
            model_name="knowledgedocument",
            name="source_file",
            field=models.FileField(blank=True, null=True, upload_to="knowledge_sources/"),
        ),
        migrations.AddField(
            model_name="knowledgedocument",
            name="source_filename",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="knowledgedocument",
            name="source_type",
            field=models.CharField(blank=True, default="text", max_length=32),
        ),
        migrations.AddField(
            model_name="aiconfiguration",
            name="request_limit",
            field=models.PositiveIntegerField(default=100),
        ),
        migrations.AddField(
            model_name="aiconfiguration",
            name="requests_used",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="aiconfiguration",
            name="token_limit",
            field=models.PositiveIntegerField(default=100000),
        ),
        migrations.AddField(
            model_name="aiconfiguration",
            name="tokens_used",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
