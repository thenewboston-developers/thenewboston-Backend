# Generated by Django 4.2.3 on 2024-01-12 01:29

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('ia', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Message',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_date', models.DateTimeField(auto_now_add=True)),
                ('modified_date', models.DateTimeField(auto_now=True)),
                (
                    'sender_type',
                    models.CharField(choices=[('IA', 'Ia'), ('USER', 'User')], default='USER', max_length=4)
                ),
                ('text', models.TextField()),
                (
                    'conversation',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name='messages', to='ia.conversation'
                    )
                ),
                (
                    'sender',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to=settings.AUTH_USER_MODEL
                    )
                ),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
