# Generated by Django 4.2.2 on 2023-06-28 21:12

from django.db import migrations, models

import thenewboston.general.validators


class Migration(migrations.Migration):

    dependencies = [
        ('wallets', '0004_remove_wallet_unique_user_core_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='wallet',
            name='deposit_account_number',
            field=models.CharField(
                default='d42a7ec1d703ab3c82c944fa262c62609abb351f0a20b4266219026f35f1804d',
                max_length=64,
                validators=[thenewboston.general.validators.HexStringValidator(64)]
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='wallet',
            name='deposit_balance',
            field=models.PositiveBigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='wallet',
            name='deposit_signing_key',
            field=models.CharField(
                default='d42a7ec1d703ab3c82c944fa262c62609abb351f0a20b4266219026f35f1804d',
                max_length=64,
                validators=[thenewboston.general.validators.HexStringValidator(64)]
            ),
            preserve_default=False,
        ),
        migrations.DeleteModel(name='DepositAccount',),
    ]
