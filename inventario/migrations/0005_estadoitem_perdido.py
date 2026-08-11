"""
0005_estadoitem_perdido.py — inventario
Migración de datos: asegura que exista el EstadoItem "Perdido", usado por
FinalizarInspeccionService cuando un ítem se marca 'no_entregado' en una
inspección de devolución. EstadoItem no tiene choices fijos (es una tabla
catálogo con nombre libre) — sin esta fila, cualquier BD que no haya
corrido `seed_e2e` no tendría este estado disponible.
"""
from django.db import migrations


def crear_estado_perdido(apps, schema_editor):
    EstadoItem = apps.get_model('inventario', 'EstadoItem')
    EstadoItem.objects.get_or_create(nombre='Perdido')


def eliminar_estado_perdido(apps, schema_editor):
    # No-op deliberado: ItemInventario.estado es on_delete=CASCADE, así que
    # borrar esta fila borraría en cascada cualquier ítem marcado "Perdido"
    # con él. Revertir esta migración no debería destruir inventario real.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0004_estadoinsumo_insumo_estado'),
    ]

    operations = [
        migrations.RunPython(crear_estado_perdido, eliminar_estado_perdido),
    ]
