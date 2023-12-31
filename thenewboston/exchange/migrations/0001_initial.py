# Generated by Django 4.2.3 on 2023-07-29 16:47

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('cores', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ExchangeOrder',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_date', models.DateTimeField(auto_now_add=True)),
                ('modified_date', models.DateTimeField(auto_now=True)),
                ('order_type', models.CharField(choices=[('BUY', 'Buy'), ('SELL', 'Sell')], max_length=4)),
                ('quantity', models.PositiveBigIntegerField(validators=[django.core.validators.MinValueValidator(1)])),
                ('price', models.PositiveBigIntegerField(validators=[django.core.validators.MinValueValidator(1)])),
                ('filled_amount', models.PositiveBigIntegerField(default=0)),
                (
                    'fill_status',
                    models.CharField(
                        choices=[('OPEN', 'Open'), ('PARTIALLY_FILLED', 'Partially Filled'), ('FILLED', 'Filled'),
                                 ('CANCELLED', 'Cancelled')],
                        default='OPEN',
                        max_length=16
                    )
                ),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                (
                    'primary_currency',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name='primary_orders', to='cores.core'
                    )
                ),
                (
                    'secondary_currency',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name='secondary_orders', to='cores.core'
                    )
                ),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='Trade',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_date', models.DateTimeField(auto_now_add=True)),
                ('modified_date', models.DateTimeField(auto_now=True)),
                ('fill_quantity', models.PositiveBigIntegerField()),
                ('trade_price', models.PositiveBigIntegerField()),
                ('overpayment_amount', models.PositiveBigIntegerField()),
                (
                    'buy_order',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='buy_trades',
                        to='exchange.exchangeorder'
                    )
                ),
                (
                    'sell_order',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='sell_trades',
                        to='exchange.exchangeorder'
                    )
                ),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='AssetPair',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                (
                    'primary_currency',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='primary_asset_pairs',
                        to='cores.core'
                    )
                ),
                (
                    'secondary_currency',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='secondary_asset_pairs',
                        to='cores.core'
                    )
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name='assetpair',
            constraint=models.UniqueConstraint(
                fields=('primary_currency', 'secondary_currency'), name='unique_asset_pair'
            ),
        ),
    ]
