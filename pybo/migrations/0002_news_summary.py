# Generated by Django 5.0.4 on 2024-05-14 07:26

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pybo', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='news',
            name='summary',
            field=models.URLField(default=1),
            preserve_default=False,
        ),
    ]