"""
Fase Personal, etapa 3: elimina los modelos de personas sin cuenta
Laboratorista (cédula, programa, responsabilidades) y LaboratoristaLab
(asignaciones laboratorista/encargado). Sus filas ya se borraron en la 0023;
las personas monitor ahora son FichaMonitor y los laboratoristas son cuentas
de Usuario (Laboratorio.laboratoristas).

No toca ninguna cuenta de Usuario. Reversa: recrea las dos tablas vacías.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('laboratorio', '0024_laboratorista_un_solo_laboratorio'),
    ]

    operations = [
        migrations.DeleteModel(name='LaboratoristaLab'),
        migrations.DeleteModel(name='Laboratorista'),
    ]
