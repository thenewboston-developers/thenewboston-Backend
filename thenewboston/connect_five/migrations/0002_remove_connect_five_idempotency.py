from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('connect_five', '0001_initial'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='connectfiveledgerentry',
            name='unique_connect_five_ledger_idempotency',
        ),
        migrations.RemoveField(
            model_name='connectfiveledgerentry',
            name='idempotency_key',
        ),
        migrations.RemoveField(
            model_name='connectfivematchevent',
            name='idempotency_key',
        ),
        migrations.DeleteModel(
            name='ConnectFiveIdempotencyKey',
        ),
    ]
