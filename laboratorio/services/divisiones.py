"""
divisiones.py — laboratorio
Divisiones (salones) dentro de la sala de un laboratorio y guardado del
editor de mapa.

- crear_division(): alta individual respetando el máximo por laboratorio.
- guardar_mapa(): lo que envía el editor (posiciones y categoría de módulos +
  el conjunto completo de divisiones) se valida entero — incluido que ningún
  módulo quede fuera del lienzo ni sobre otro — y se aplica en una
  transacción: todo o nada.
- division_para(): a qué división pertenece un módulo según su posición.

Regla de pertenencia: un módulo pertenece a la división que contiene su
centro. Un módulo sin posición guardada (0, 0 — ver posiciones_mapa.sin_posicion)
no pertenece a ninguna: no está "dibujado" en ningún lugar del editor.
"""
from django.core.exceptions import ValidationError
from django.db import transaction

from laboratorio.models import Division, Modulo
from laboratorio.services.posiciones_mapa import (
    ALTO_MODULO, ANCHO_MODULO, LIENZO_EDITOR_ALTO, LIENZO_EDITOR_ANCHO, modulo_en_lienzo, pares_solapados,
)


class MapaInvalido(Exception):
    """Datos del editor que no se pueden guardar. El mensaje va al usuario."""


def crear_division(laboratorio, nombre, x=0, y=0, ancho=300, alto=200):
    """Crea una división validando el modelo (incluido el máximo de
    Division.MAX_POR_LABORATORIO). Lanza ValidationError si no se puede."""
    with transaction.atomic():
        # select_for_update sobre el laboratorio serializa altas concurrentes
        # del mismo laboratorio, para que dos no pasen el conteo a la vez.
        type(laboratorio).objects.select_for_update().filter(pk=laboratorio.pk).exists()
        if laboratorio.divisiones.count() >= Division.MAX_POR_LABORATORIO:
            raise ValidationError(
                f'Un laboratorio puede tener como máximo {Division.MAX_POR_LABORATORIO} divisiones.'
            )
        division = Division(laboratorio=laboratorio, nombre=(nombre or '').strip(),
                            x=x, y=y, ancho=ancho, alto=alto)
        division.full_clean()
        division.save()
    return division


def division_para(x, y, divisiones):
    """La división que contiene el centro de un módulo en (x, y), o None."""
    if x == 0 and y == 0:
        return None
    centro_x, centro_y = x + ANCHO_MODULO // 2, y + ALTO_MODULO // 2
    for division in divisiones:
        if division.contiene(centro_x, centro_y):
            return division
    return None


def _entero(valor, campo):
    try:
        return int(valor)
    except (TypeError, ValueError):
        raise MapaInvalido(f'Valor inválido para "{campo}": {valor!r}.')


def _leer_divisiones(laboratorio, entradas):
    """Lista de Division (sin guardar) que reemplazará a las actuales."""
    if not isinstance(entradas, list):
        raise MapaInvalido('"divisiones" debe ser una lista.')
    if len(entradas) > Division.MAX_POR_LABORATORIO:
        raise MapaInvalido(
            f'Un laboratorio puede tener como máximo {Division.MAX_POR_LABORATORIO} divisiones '
            f'(se enviaron {len(entradas)}).'
        )

    actuales = {d.id: d for d in laboratorio.divisiones.all()}
    resultado, nombres = [], set()
    for entrada in entradas:
        if not isinstance(entrada, dict):
            raise MapaInvalido('Cada división debe ser un objeto {id, nombre, x, y, ancho, alto}.')
        id_ = entrada.get('id')
        if id_ in (None, ''):
            division = Division(laboratorio=laboratorio)
        else:
            id_ = _entero(id_, 'id')
            if id_ not in actuales:
                raise MapaInvalido(f'La división {id_} no pertenece a este laboratorio.')
            division = actuales[id_]

        division.nombre = str(entrada.get('nombre', '')).strip()
        division.x = _entero(entrada.get('x'), 'x')
        division.y = _entero(entrada.get('y'), 'y')
        division.ancho = _entero(entrada.get('ancho'), 'ancho')
        division.alto = _entero(entrada.get('alto'), 'alto')

        clave = division.nombre.casefold()
        if clave in nombres:
            raise MapaInvalido(f'Hay dos divisiones llamadas "{division.nombre}".')
        nombres.add(clave)
        # Sin el máximo por laboratorio (ya validado arriba sobre el conjunto
        # final) ni la unicidad en BD (los nombres pueden intercambiarse
        # entre divisiones en el mismo guardado; se validan arriba).
        errores = list(division.errores_de_datos().values())
        try:
            division.clean_fields(exclude=['laboratorio'])
        except ValidationError as e:
            errores.extend(e.messages)
        if errores:
            raise MapaInvalido(f'División "{division.nombre or "sin nombre"}": ' + ' '.join(errores))
        resultado.append(division)

    for i, a in enumerate(resultado):
        for b in resultado[i + 1:]:
            if a.se_superpone(b):
                raise MapaInvalido(f'Las divisiones "{a.nombre}" y "{b.nombre}" se superponen.')
    return resultado


MAX_PARES_EN_MENSAJE = 5


def _leer_modulos(datos):
    """{id: (x, y)} y {id: categoria_id | None} (solo de las entradas que
    traen la clave "categoria") de la lista "modulos" del editor."""
    if not isinstance(datos, dict) or not isinstance(datos.get('modulos'), list):
        raise MapaInvalido('Datos inválidos: se esperaba {"modulos": [{"id", "x", "y"}, ...]}.')
    posiciones, categorias = {}, {}
    for entrada in datos['modulos']:
        try:
            id_ = int(entrada['id'])
            posiciones[id_] = (int(entrada['x']), int(entrada['y']))
        except (ValueError, KeyError, TypeError):
            raise MapaInvalido('Datos inválidos: se esperaba {"modulos": [{"id", "x", "y"}, ...]}.')
        if 'categoria' in entrada:
            categorias[id_] = None if entrada['categoria'] in (None, '') else _entero(entrada['categoria'], 'categoria')
    if any(x < 0 or y < 0 for x, y in posiciones.values()):
        raise MapaInvalido('Las posiciones no pueden ser negativas.')
    return posiciones, categorias


def _validar_categorias(modulos, categorias):
    """{id de módulo: CategoriaModulo | None}. Solo categorías activas, salvo
    la que el módulo ya tiene (aunque se haya desactivado después)."""
    from laboratorio.models import CategoriaModulo

    existentes = CategoriaModulo.objects.in_bulk({c for c in categorias.values() if c is not None})
    por_id = {m.id: m for m in modulos}
    resultado = {}
    for modulo_id, categoria_id in categorias.items():
        if categoria_id is None:
            resultado[modulo_id] = None
            continue
        categoria = existentes.get(categoria_id)
        if categoria is None:
            raise MapaInvalido(f'La categoría {categoria_id} no existe.')
        if not categoria.activo and por_id[modulo_id].categoria_id != categoria_id:
            raise MapaInvalido(f'La categoría "{categoria.nombre}" está desactivada.')
        resultado[modulo_id] = categoria
    return resultado


def guardar_mapa(laboratorio, datos):
    """Aplica lo que envía el editor:

        {"modulos": [{"id", "x", "y", "categoria" (opcional: id | null)}, ...],
         "divisiones": [{"id" (opcional), "nombre", "x", "y", "ancho", "alto"}, ...]}

    Valida TODO antes de escribir y lanza MapaInvalido sin tocar nada si:
    - una posición es negativa o MUEVE al módulo fuera del lienzo del editor,
    - dos módulos del laboratorio se solapan (con su posición final; los que
      siguen sin posición, en (0, 0), no cuentan),
    - una categoría no existe o está desactivada,
    - una división es inválida o dos se superponen.

    "divisiones" es opcional; si viene, es el conjunto COMPLETO: las que no
    aparecen se eliminan (sus módulos quedan sin división, no se borran).
    Después se reasigna la división de todos los módulos según su posición
    (mover una división no mueve sus módulos). Devuelve (módulos enviados,
    divisiones resultantes)."""
    posiciones, categorias = _leer_modulos(datos)

    with transaction.atomic():
        modulos = list(laboratorio.modulos.select_for_update())
        por_id = {m.id: m for m in modulos}
        ajenos = sorted(set(posiciones) - set(por_id))
        if ajenos:
            raise MapaInvalido(f'Módulos que no pertenecen a este laboratorio: {ajenos}.')

        # Solo posiciones NUEVAS fuera del lienzo: un módulo guardado antes de
        # que el lienzo tuviera tamaño fijo y que sigue donde estaba no bloquea
        # el guardado (el editor avisa para que se traiga adentro).
        fuera = [por_id[i].nombre for i, (x, y) in posiciones.items()
                 if (x, y) != (por_id[i].posicion_x, por_id[i].posicion_y)
                 and not (x == 0 and y == 0) and not modulo_en_lienzo(x, y)]
        if fuera:
            raise MapaInvalido(
                f'Módulos fuera del lienzo ({LIENZO_EDITOR_ANCHO}×{LIENZO_EDITOR_ALTO} px): '
                + ', '.join(f'"{n}"' for n in fuera) + '.'
            )

        finales = [(m, *posiciones.get(m.id, (m.posicion_x, m.posicion_y))) for m in modulos]
        pares = pares_solapados(finales)
        if pares:
            detalle = ', '.join(f'"{a.nombre}" y "{b.nombre}"' for a, b in pares[:MAX_PARES_EN_MENSAJE])
            resto = len(pares) - MAX_PARES_EN_MENSAJE
            raise MapaInvalido(
                f'Hay módulos que se solapan: {detalle}' + (f' (y {resto} par(es) más)' if resto > 0 else '')
                + '. Muévelos antes de guardar.'
            )

        nuevas_categorias = _validar_categorias(modulos, categorias)

        if 'divisiones' in datos:
            divisiones = _leer_divisiones(laboratorio, datos['divisiones'])
        else:
            divisiones = list(laboratorio.divisiones.all())

        # ── A partir de acá solo escrituras: todo ya se validó. ──
        if 'divisiones' in datos:
            conservadas = {d.id for d in divisiones if d.pk}
            # SET_NULL: los módulos de las divisiones eliminadas quedan sin división.
            laboratorio.divisiones.exclude(id__in=conservadas).delete()
            # Nombres temporales primero: permite intercambiar nombres entre
            # divisiones existentes sin chocar con la restricción de unicidad.
            for d in divisiones:
                if d.pk:
                    Division.objects.filter(pk=d.pk).update(nombre=f'__tmp_{d.pk}')
            for d in divisiones:
                d.save()

        for modulo, x, y in finales:
            modulo.posicion_x, modulo.posicion_y = x, y
            modulo.division = division_para(x, y, divisiones)
            if modulo.id in nuevas_categorias:
                modulo.categoria = nuevas_categorias[modulo.id]
        Modulo.objects.bulk_update(modulos, ['posicion_x', 'posicion_y', 'division', 'categoria'])

    return [m for m in modulos if m.id in posiciones], divisiones
