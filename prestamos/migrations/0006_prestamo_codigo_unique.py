from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('prestamos', '0005_generar_codigos_existentes'),
    ]

    operations = [
        migrations.AlterField(
            model_name='prestamo',
            name='codigo',
            field=models.CharField(blank=True, default='', max_length=50, unique=True),
        ),
    ]
