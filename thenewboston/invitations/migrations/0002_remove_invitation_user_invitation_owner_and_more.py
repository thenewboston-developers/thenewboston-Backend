# Generated by Django 4.2.3 on 2023-07-30 20:30

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('invitations', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='invitation',
            name='user',
        ),
        migrations.AddField(
            model_name='invitation',
            name='owner',
            field=models.ForeignKey(
                default=1,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='invitations_created',
                to=settings.AUTH_USER_MODEL
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='invitation',
            name='recipient',
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='invitation_received',
                to=settings.AUTH_USER_MODEL
            ),
        ),
        migrations.CreateModel(
            name='InvitationLimit',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.PositiveIntegerField()),
                (
                    'owner',
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='invitation_limit',
                        to=settings.AUTH_USER_MODEL
                    )
                ),
            ],
        ),
    ]