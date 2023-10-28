# Generated by Django 4.2.3 on 2023-10-28 19:17

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('art', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ArtworkTransfer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_date', models.DateTimeField(auto_now_add=True)),
                ('modified_date', models.DateTimeField(auto_now=True)),
                ('artwork', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='art.artwork')),
                (
                    'new_owner',
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='acquired_artworks',
                        to=settings.AUTH_USER_MODEL
                    )
                ),
                (
                    'previous_owner',
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='transferred_artworks',
                        to=settings.AUTH_USER_MODEL
                    )
                ),
            ],
            options={
                'abstract': False,
            },
        ),
    ]