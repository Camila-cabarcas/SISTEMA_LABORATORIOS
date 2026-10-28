"""
Siembra las categorías base de módulo. Idempotente: busca por nombre (sin
distinguir mayúsculas) y solo crea las que faltan — nunca pisa el color o la
forma que un Administrador haya cambiado, ni reactiva una desactivada.
"""
from django.db import migrations

CATEGORIAS_BASE = [
    # (nombre, color, forma)
    ('Mesa', '#0d6efd', 'cuadrado'),          # azul, forma original del módulo
    ('Computador', '#198754', 'computador'),  # verde
    ('Maquinaria', '#fd7e14', 'maquinaria'),  # naranja
]


def sembrar_categorias(apps, schema_editor):
    CategoriaModulo = apps.get_model('laboratorio', 'CategoriaModulo')
    for nombre, color, forma in CATEGORIAS_BASE:
        if not CategoriaModulo.objects.filter(nombre__iexact=nombre).exists():
            CategoriaModulo.objects.create(nombre=nombre, color=color, forma=forma, activo=True)


class Migration(migrations.Migration):

    dependencies = [
        ('laboratorio', '0017_categoriamodulo'),
    ]

    operations = [
        # Revertir no borra nada: las categorías pueden tener módulos (PROTECT).
        migrations.RunPython(sembrar_categorias, migrations.RunPython.noop),
    ]
