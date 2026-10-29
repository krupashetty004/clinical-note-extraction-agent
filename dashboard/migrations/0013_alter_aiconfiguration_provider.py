from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0012_alter_clinicalprocessingrun_execution_mode"),
    ]

    operations = [
        migrations.AlterField(
            model_name="aiconfiguration",
            name="provider",
            field=models.CharField(
                choices=[
                    ("synthetic", "Local synthetic test provider"),
                    ("groq", "Groq"),
                    ("gemini", "Google Gemini"),
                ],
                max_length=32,
            ),
        ),
    ]
