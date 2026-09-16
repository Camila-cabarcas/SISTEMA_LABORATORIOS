"""
crear_insumos_por_lab.py — inventario
Comando de management que puebla cada Laboratorio activo con un catálogo de
insumos típicos (elegido por palabras clave en el nombre del laboratorio) y
2-3 ItemInventario por insumo, con una distribución de estados realista
(mayoría Disponible, algunos Prestado/Dañado/Perdido) — para tener datos de
demo con los que probar el sistema de stock (Insumo.stock_disponible(),
PrestamoStockService, etc.) sin tener que cargarlos a mano.

Idempotente: usa get_or_create tanto para Insumo (nombre, laboratorio) como
para ItemInventario (codigo) — correrlo varias veces no duplica nada; si un
insumo ya existe para ese laboratorio, solo se asegura que tenga ítems.

Uso: python manage.py crear_insumos_por_lab [--items-por-insumo 3]
"""
import random
import unicodedata

from django.core.management.base import BaseCommand
from django.db import transaction

# Catálogo de insumos típicos por tipo de laboratorio, elegido por palabras
# clave (normalizadas: minúsculas, sin tildes) que deben aparecer en
# Laboratorio.nombre. Se evalúa en orden — las combinaciones más específicas
# ("ingenieria" + "sistemas") van antes que las genéricas ("sistemas" sola),
# para no confundir "Laboratorio de Ingeniería de Sistemas" con un
# "Laboratorio de Sistemas" de electrónica.
CATALOGO_POR_PALABRAS_CLAVE = [
    (('ingenieria', 'sistemas'), [
        'Laptop', 'Monitor', 'Router', 'Teclado', 'Mouse', 'Cable HDMI', 'Switch de red',
    ]),
    (('mecanica',), [
        'Destornillador plano', 'Destornillador de estrella', 'Llave inglesa',
        'Martillo', 'Metro', 'Calibrador Vernier', 'Alicate',
    ]),
    (('ondas',), [
        'Osciloscopio', 'Generador de señales', 'Sonda de osciloscopio',
        'Multímetro', 'Fuente DC', 'Cable BNC',
    ]),
    (('fisica',), [
        'Osciloscopio', 'Generador de señales', 'Multímetro', 'Fuente DC',
        'Cronómetro', 'Riel de aire',
    ]),
    (('quimica',), [
        'Vaso precipitado', 'Matraz Erlenmeyer', 'Probeta', 'Pipeta',
        'Balanza analítica', 'Mechero',
    ]),
    (('sistemas',), [
        'Cable de red', 'Router', 'Switch', 'Placa de desarrollo',
        'Kit de componentes electrónicos', 'Protoboard',
    ]),
    (('electronica',), [
        'Multímetro', 'Protoboard', 'Kit de componentes electrónicos',
        'Fuente DC', 'Cautín',
    ]),
]

CATALOGO_GENERICO = [
    'Multímetro', 'Cable USB', 'Extensión eléctrica', 'Caja de herramientas',
    'Guantes de protección',
]

# Distribución de estados de los ItemInventario creados: mayoría Disponible,
# el resto repartido entre Prestado/Dañado/Perdido — no son todos
# 'Disponible' a propósito, para que el stock de demo ya muestre la
# diferencia entre stock_total() y stock_disponible().
ESTADOS_CON_PESO = [
    ('Disponible', 70),
    ('Prestado', 15),
    ('Dañado', 10),
    ('Perdido', 5),
]


def _normalizar(texto):
    sin_tildes = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode('ascii')
    return sin_tildes.lower()


def _catalogo_para(laboratorio_nombre):
    normalizado = _normalizar(laboratorio_nombre)
    for palabras_clave, catalogo in CATALOGO_POR_PALABRAS_CLAVE:
        if all(palabra in normalizado for palabra in palabras_clave):
            return catalogo
    return CATALOGO_GENERICO


class Command(BaseCommand):
    help = (
        'Crea insumos típicos (5-10 por laboratorio) con 2-3 ItemInventario '
        'cada uno, para cada Laboratorio activo que todavía no tenga insumos propios.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--items-por-insumo', type=int, default=3,
            help='Cuántos ItemInventario crear por insumo (default: 3).',
        )
        parser.add_argument(
            '--seed', type=int, default=None,
            help='Semilla para random (reproducible); si se omite, cada corrida varía.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        from inventario.models import EstadoInsumo, EstadoItem, Insumo, ItemInventario, MovimientoInventario, TipoMovimiento
        from laboratorio.models import Laboratorio
        from users.models import Rol, Usuario

        if options['seed'] is not None:
            random.seed(options['seed'])

        items_por_insumo = max(2, min(options['items_por_insumo'], 3))

        for nombre in ['Disponible', 'Prestado', 'Dañado', 'Perdido']:
            EstadoItem.objects.get_or_create(nombre=nombre)
        estado_activo_insumo, _ = EstadoInsumo.objects.get_or_create(nombre='Activo')
        tipo_registro, _ = TipoMovimiento.objects.get_or_create(nombre='Registro inicial')
        estados_item = {e.nombre: e for e in EstadoItem.objects.all()}

        # Usuario responsable de los movimientos de "alta inicial" — se
        # reutiliza el primer Administrador que exista; si no hay ninguno
        # (proyecto recién clonado), se crea uno de seed dedicado, igual que
        # seed_e2e.py hace con sus propios usuarios de prueba.
        rol_admin, _ = Rol.objects.get_or_create(nombre='Administrador')
        usuario_seed = Usuario.objects.filter(rol__nombre='Administrador').order_by('id').first()
        if usuario_seed is None:
            usuario_seed, _ = Usuario.objects.get_or_create(
                username='seed_inventario',
                defaults={'rol': rol_admin, 'codigo': 'SEED-INV', 'is_staff': True},
            )

        laboratorios = Laboratorio.objects.filter(activo=True)
        if not laboratorios.exists():
            self.stdout.write(self.style.WARNING(
                'No hay laboratorios activos — nada que poblar.'
            ))
            return

        total_insumos_creados = 0
        total_items_creados = 0

        for laboratorio in laboratorios:
            catalogo = _catalogo_para(laboratorio.nombre)

            for nombre_insumo in catalogo:
                insumo, insumo_creado = Insumo.objects.get_or_create(
                    nombre=nombre_insumo,
                    laboratorio=laboratorio,
                    defaults={
                        'descripcion': f'{nombre_insumo} — {laboratorio.nombre}',
                        'estado': estado_activo_insumo,
                        'stock_minimo': 1,
                    },
                )
                if insumo_creado:
                    total_insumos_creados += 1

                items_existentes = insumo.stock_total()
                items_a_crear = max(items_por_insumo - items_existentes, 0)

                for i in range(items_a_crear):
                    numero = items_existentes + i + 1
                    codigo = f"{laboratorio.id}-{_normalizar(nombre_insumo).replace(' ', '-')}-{numero:03d}"

                    nombre_estado = random.choices(
                        [n for n, _ in ESTADOS_CON_PESO],
                        weights=[p for _, p in ESTADOS_CON_PESO],
                    )[0]

                    item, item_creado = ItemInventario.objects.get_or_create(
                        codigo=codigo,
                        defaults={
                            'insumo': insumo,
                            'estado': estados_item[nombre_estado],
                            'laboratorio': laboratorio,
                            'updated_by': usuario_seed,
                        },
                    )
                    if item_creado:
                        total_items_creados += 1
                        MovimientoInventario.objects.create(
                            item_inventario=item,
                            usuario=usuario_seed,
                            tipo_movimiento=tipo_registro,
                            observacion=f'Alta inicial — estado {nombre_estado}.',
                        )

            self.stdout.write(
                f'{laboratorio.nombre}: catálogo de {len(catalogo)} insumo(s) asegurado.'
            )

        self.stdout.write(self.style.SUCCESS(
            f'Listo. Insumos nuevos: {total_insumos_creados}. '
            f'Ítems nuevos: {total_items_creados}.'
        ))
