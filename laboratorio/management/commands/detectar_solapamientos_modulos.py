"""
detectar_solapamientos_modulos.py — laboratorio
Lista los pares de módulos que se solapan en el mapa (mismo tamaño y misma
regla que el guardado del editor: laboratorio.services.posiciones_mapa).
SOLO LECTURA: no mueve ni modifica nada; sirve para encontrar los datos que
el editor ya no dejará guardar hasta que se separen.

    python manage.py detectar_solapamientos_modulos
    python manage.py detectar_solapamientos_modulos --laboratorio 3

Los módulos en (0, 0) ("sin posición guardada") no cuentan.
"""
from types import SimpleNamespace

from django.core.management.base import BaseCommand, CommandError

from laboratorio.models import Laboratorio, Modulo
from laboratorio.services.posiciones_mapa import pares_solapados


class Command(BaseCommand):

    help = 'Lista los pares de módulos que se solapan en el mapa (solo lectura, no modifica nada).'

    def add_arguments(self, parser):
        parser.add_argument('--laboratorio', type=int, help='Revisar solo este laboratorio (id).')

    def handle(self, *args, **options):
        laboratorios = Laboratorio.objects.order_by('id')
        if options['laboratorio'] is not None:
            laboratorios = laboratorios.filter(id=options['laboratorio'])
            if not laboratorios.exists():
                raise CommandError(f'No existe el laboratorio {options["laboratorio"]}.')

        # values(): solo las columnas necesarias, sin cargar ni guardar modelos.
        filas = (Modulo.objects.filter(laboratorio__in=laboratorios)
                 .order_by('laboratorio_id', 'id')
                 .values('id', 'nombre', 'laboratorio_id', 'posicion_x', 'posicion_y'))
        por_lab = {}
        for f in filas:
            por_lab.setdefault(f['laboratorio_id'], []).append(
                (SimpleNamespace(id=f['id'], nombre=f['nombre']), f['posicion_x'], f['posicion_y'])
            )

        total = 0
        for lab in laboratorios:
            pares = pares_solapados(por_lab.get(lab.id, []))
            if not pares:
                continue
            total += len(pares)
            posicion = {m.id: (x, y) for m, x, y in por_lab[lab.id]}
            self.stdout.write(self.style.WARNING(f'{lab.nombre} (id {lab.id}): {len(pares)} par(es) solapado(s)'))
            for a, b in pares:
                self.stdout.write(
                    f'  - "{a.nombre}" (id {a.id}, {posicion[a.id][0]},{posicion[a.id][1]})'
                    f' ↔ "{b.nombre}" (id {b.id}, {posicion[b.id][0]},{posicion[b.id][1]})'
                )

        if total:
            self.stdout.write(self.style.WARNING(f'{total} par(es) de módulos solapados en total. No se modificó nada.'))
            return
        self.stdout.write(self.style.SUCCESS('No hay módulos solapados.'))
