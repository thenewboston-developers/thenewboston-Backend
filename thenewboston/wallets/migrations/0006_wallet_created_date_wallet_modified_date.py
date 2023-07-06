# Generated by Django 4.2.2 on 2023-07-05 18:10

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('wallets', '0005_wallet_deposit_account_number_wallet_deposit_balance_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='wallet',
            name='created_date',
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='wallet',
            name='modified_date',
            field=models.DateTimeField(auto_now=True),
        ),
    ]