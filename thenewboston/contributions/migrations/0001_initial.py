# Generated by Django 4.2.3 on 2024-01-15 20:24

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('github', '0002_alter_githubuser_options'),
        ('cores', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Contribution',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_date', models.DateTimeField(auto_now_add=True)),
                ('modified_date', models.DateTimeField(auto_now=True)),
                ('reward_amount', models.PositiveBigIntegerField()),
                ('core', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='cores.core')),
                (
                    'github_user',
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='github.githubuser')
                ),
                ('issue', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='github.issue')),
                ('pull', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='github.pull')),
                ('repo', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='github.repo')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
