"""
inicializar_posiciones_modulos.py — laboratorio
Da una posición inicial (posicion_x/posicion_y) a los módulos que siguen en
(0, 0), para que el editor de mapa (editar_mapa_laboratorio) no los muestre
amontonados en la esquina.

Uso:
    python manage.py inicializar_posiciones_modulos [--dry-run] [--laboratorio ID]

Reparto: el diseño por defecto de laboratorio/services/posiciones_mapa.py,
que replica el del mapa por zonas. No se usa Modulo.zona: el mapa lo ignora
y en la práctica todos los módulos tienen el valor por defecto
('centro-mid'). Así las posiciones iniciales coinciden con lo que el mapa ya
muestra.

Idempotente: solo escribe módulos en (0, 0). El cálculo es determinista
(depende solo del orden de los módulos de cada laboratorio), así que
correrlo de nuevo no cambia nada.
"""
from itertools import groupby

from django.core.management.base import BaseCommand
from django.db import transaction

from laboratorio.models import Modulo
from laboratorio.services.posiciones_mapa import calcular_posiciones, sin_posicion


class Command(BaseCommand):
    help = 'Da posición inicial en el mapa a los módulos que siguen en (0, 0), por laboratorio.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true',
                            help='Muestra qué se haría sin guardar nada.')
        parser.add_argument('--laboratorio', type=int, metavar='ID',
                            help='Solo este laboratorio.')

    @transaction.atomic
    def handle(self, *args, **options):
        modulos = Modulo.objects.select_related('laboratorio').order_by('laboratorio_id', 'id')
        if options['laboratorio']:
            modulos = modulos.filter(laboratorio_id=options['laboratorio'])

        a_guardar = []
        for _, grupo in groupby(modulos, key=lambda m: m.laboratorio_id):
            del_lab = list(grupo)
            pendientes = 0
            for modulo, (x, y) in zip(del_lab, calcular_posiciones(len(del_lab))):
                if sin_posicion(modulo):
                    modulo.posicion_x, modulo.posicion_y = x, y
                    a_guardar.append(modulo)
                    pendientes += 1
            self.stdout.write(
                f'  {del_lab[0].laboratorio.nombre}: {pendientes} de {len(del_lab)} módulos a inicializar'
            )

        if options['dry_run']:
            self.stdout.write(self.style.WARNING(f'Dry run: se inicializarían {len(a_guardar)} módulos.'))
            return

        Modulo.objects.bulk_update(a_guardar, ['posicion_x', 'posicion_y'])
        self.stdout.write(self.style.SUCCESS(f'Total: {len(a_guardar)} módulos inicializados.'))
