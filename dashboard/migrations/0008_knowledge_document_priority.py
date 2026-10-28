from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0007_knowledge_document"),
    ]

    operations = [
        migrations.AddField(
            model_name="knowledgedocument",
            name="priority",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Higher values appear first when sorted by priority.",
            ),
        ),
    ]
