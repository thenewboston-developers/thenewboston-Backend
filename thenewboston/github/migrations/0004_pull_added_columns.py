# Generated by Django 4.2.3 on 2024-04-03 14:48

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('github', '0003_various_changes'),
    ]

    operations = [
        migrations.AddField(
            model_name='pull',
            name='assessment_points',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='pull',
            name='assessment_explanation',
            field=models.TextField(blank=True, null=True),
        ),
    ]
