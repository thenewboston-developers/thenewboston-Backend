# Generated by Django 4.2.2 on 2023-06-20 18:52

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import thenewboston.general.validators


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='DepositAccount',
            fields=[
                (
                    'user',
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        primary_key=True,
                        serialize=False,
                        to=settings.AUTH_USER_MODEL
                    )
                ),
                (
                    'account_number',
                    models.CharField(
                        max_length=64, validators=[thenewboston.general.validators.HexStringValidator(64)]
                    )
                ),
                (
                    'signing_key',
                    models.CharField(
                        max_length=64, validators=[thenewboston.general.validators.HexStringValidator(64)]
                    )
                ),
            ],
        ),
    ]
