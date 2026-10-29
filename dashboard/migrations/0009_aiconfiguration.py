from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0008_knowledge_document_priority"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AIConfiguration",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider", models.CharField(choices=[("synthetic", "Local synthetic test provider"), ("groq", "Groq")], max_length=32)),
                ("model", models.CharField(max_length=120)),
                ("temperature", models.DecimalField(decimal_places=2, default=0, max_digits=3)),
                ("max_tokens", models.PositiveIntegerField(default=2048)),
                ("version_number", models.PositiveIntegerField(default=1)),
                ("is_active", models.BooleanField(default=False)),
                ("last_test_status", models.CharField(default="not_tested", max_length=24)),
                ("last_test_result", models.CharField(blank=True, default="", max_length=255)),
                ("tested_at", models.DateTimeField(blank=True, null=True)),
                ("activated_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("activated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="ai_configurations_activated", to=settings.AUTH_USER_MODEL)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="ai_configurations_created", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["-updated_at", "-pk"],
            },
        ),
    ]
