# Generated by Django 4.2.2 on 2023-06-20 18:28

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Core',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_date', models.DateTimeField(auto_now_add=True)),
                ('modified_date', models.DateTimeField(auto_now=True)),
                ('domain', models.CharField(max_length=255, unique=True)),
                ('logo', models.ImageField(blank=True, upload_to='images/')),
                ('ticker', models.CharField(max_length=5, unique=True)),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
