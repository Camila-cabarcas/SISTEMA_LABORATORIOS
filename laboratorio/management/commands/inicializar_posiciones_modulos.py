"""
inicializar_posiciones_modulos.py — laboratorio
Da una posición inicial (posicion_x/posicion_y) a los módulos que siguen en
(0, 0), para que el editor de mapa (editar_mapa_laboratorio) no los muestre
amontonados en la esquina.

Uso:
    python manage.py inicializar_posiciones_modulos [--dry-run] [--laboratorio ID]

Reparto: el mismo que usa hoy templates/laboratorio/mapa.html (su JS
reparte los módulos de cada laboratorio, en orden de id, entre las 6 zonas
visuales: 18 % a cada lado, 18 % abajo y el resto en el centro). No se usa
Modulo.zona: el mapa lo ignora y en la práctica todos los módulos tienen el
valor por defecto ('centro-mid'). Así las posiciones iniciales coinciden
con lo que el mapa ya muestra.

Idempotente: solo escribe módulos en (0, 0). El cálculo es determinista
(depende solo del orden de los módulos de cada laboratorio), así que
correrlo de nuevo no cambia nada.
"""
import math
from itertools import groupby

from django.core.management.base import BaseCommand
from django.db import transaction

from laboratorio.models import Modulo

# Tamaño de .modulo-item en templates/laboratorio/editar_mapa.html.
ANCHO_MODULO = 120
ALTO_MODULO = 80
SEPARACION = 10
MARGEN = 10
ANCHO_LIENZO = 900  # cabe en el contenedor de base_general.html desde pantallas lg

PASO_X = ANCHO_MODULO + SEPARACION
PASO_Y = ALTO_MODULO + SEPARACION

ZONAS = ['izquierda', 'centro-top', 'centro-mid', 'centro-bot', 'derecha', 'inferior']


def repartir_en_zonas(total):
    """Zona de cada módulo (por índice), replicando el JS de mapa.html."""
    por_lado = max(2, math.floor(total * 0.18))
    por_fila = max(2, math.floor(total * 0.18))
    restante = total - por_lado * 2 - por_fila
    centro_t = math.floor(restante * 0.33)
    centro_b = math.floor(restante * 0.33)
    centro_m = restante - centro_t - centro_b
    cupos = [por_lado, centro_t, centro_m, centro_b, por_lado, por_fila]

    zonas = []
    for zona, cupo in zip(ZONAS, cupos):
        zonas.extend([zona] * max(0, min(cupo, total - len(zonas))))
    zonas.extend(['centro-mid'] * (total - len(zonas)))  # sobrante, igual que el JS
    return zonas


def _fila_centrada(cantidad, x_inicio, ancho):
    """x de `cantidad` módulos en una fila centrada dentro de [x_inicio, x_inicio + ancho]."""
    ocupado = cantidad * PASO_X - SEPARACION
    x0 = x_inicio + max(0, (ancho - ocupado) // 2)
    return [x0 + i * PASO_X for i in range(cantidad)]


def _bloque(cantidad, x_inicio, ancho, y_inicio):
    """Posiciones en filas centradas; devuelve (posiciones, y siguiente libre)."""
    columnas = max(1, (ancho + SEPARACION) // PASO_X)
    posiciones = []
    y = y_inicio
    for inicio in range(0, cantidad, columnas):
        n = min(columnas, cantidad - inicio)
        posiciones.extend((x, y) for x in _fila_centrada(n, x_inicio, ancho))
        y += PASO_Y
    return posiciones, y


def calcular_posiciones(total):
    """Lista de (x, y) para los `total` módulos de un laboratorio, en orden."""
    zonas = repartir_en_zonas(total)
    cantidad = {zona: zonas.count(zona) for zona in ZONAS}

    x_izq = MARGEN
    x_der = ANCHO_LIENZO - MARGEN - ANCHO_MODULO
    x_centro = x_izq + PASO_X
    ancho_centro = x_der - SEPARACION - x_centro

    por_zona = {
        'izquierda': [(x_izq, MARGEN + i * PASO_Y) for i in range(cantidad['izquierda'])],
        'derecha': [(x_der, MARGEN + i * PASO_Y) for i in range(cantidad['derecha'])],
    }
    y = MARGEN
    for zona in ('centro-top', 'centro-mid', 'centro-bot'):
        por_zona[zona], y = _bloque(cantidad[zona], x_centro, ancho_centro, y)

    y_inferior = max(
        y,
        MARGEN + cantidad['izquierda'] * PASO_Y,
        MARGEN + cantidad['derecha'] * PASO_Y,
    ) + 2 * SEPARACION
    por_zona['inferior'], _ = _bloque(
        cantidad['inferior'], MARGEN, ANCHO_LIENZO - 2 * MARGEN, y_inferior,
    )

    siguiente = {zona: iter(posiciones) for zona, posiciones in por_zona.items()}
    return [next(siguiente[zona]) for zona in zonas]


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
                if modulo.posicion_x == 0 and modulo.posicion_y == 0:
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
