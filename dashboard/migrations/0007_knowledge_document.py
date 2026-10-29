from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.core.validators import MinValueValidator


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0006_clinicalprocessingrun_review"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="KnowledgeDocument",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=200)),
                ("summary", models.TextField(blank=True)),
                ("content", models.TextField()),
                ("source_citations", models.JSONField(blank=True, default=list)),
                ("version_number", models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("deactivated_at", models.DateTimeField(blank=True, null=True)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="knowledge_documents_created", to=settings.AUTH_USER_MODEL)),
                ("deactivated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="knowledge_documents_deactivated", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-updated_at", "-pk"],
            },
        ),
    ]
