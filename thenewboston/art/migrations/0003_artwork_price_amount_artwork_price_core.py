# Generated by Django 4.2.3 on 2023-11-03 22:12

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cores', '0001_initial'),
        ('art', '0002_artworktransfer'),
    ]

    operations = [
        migrations.AddField(
            model_name='artwork',
            name='price_amount',
            field=models.PositiveBigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='artwork',
            name='price_core',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='cores.core'
            ),
        ),
    ]