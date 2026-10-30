from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0015_aiconfiguration_tested_fingerprint"),
    ]

    operations = [
        migrations.AlterField(
            model_name="aiconfiguration",
            name="provider",
            field=models.CharField(
                choices=[
                    ("synthetic", "Local synthetic test provider"),
                    ("groq", "Groq"),
                    ("gemini", "Google Gemini (adapter not implemented)"),
                ],
                max_length=32,
            ),
        ),
    ]
