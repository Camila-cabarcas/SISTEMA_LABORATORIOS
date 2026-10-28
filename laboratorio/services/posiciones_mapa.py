"""
posiciones_mapa.py — laboratorio
Diseño por defecto del mapa de módulos: la posición (x, y) en píxeles que
le corresponde a cada módulo de un laboratorio cuando no tiene una guardada
en Modulo.posicion_x/posicion_y.

Replica el reparto del JS de templates/laboratorio/mapa.html (modo por
zonas): los módulos, en orden de id, se reparten entre las 6 zonas visuales
(18 % a cada lado, 18 % abajo y el resto en el centro). Lo usan el comando
inicializar_posiciones_modulos y mapa_laboratorio (modo por posiciones).
"""
import math

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


def sin_posicion(modulo):
    """(0, 0) es el valor por defecto de los campos: "sin posición guardada"."""
    return modulo.posicion_x == 0 and modulo.posicion_y == 0


# ── Lienzo del editor y solapamientos ─────────────────────────────────────
# Tamaño FIJO del lienzo del editor de mapa, el mismo en el navegador
# (templates/laboratorio/editar_mapa.html lo recibe por contexto) y en el
# servidor, que rechaza lo que quede fuera. Distinto de ANCHO_LIENZO, que es
# solo el ancho del diseño por defecto (calcular_posiciones).
LIENZO_EDITOR_ANCHO = 1200
LIENZO_EDITOR_ALTO = 800


def se_solapan(a, b):
    """True si dos rectángulos (x, y, ancho, alto) comparten área. Tocarse
    por un borde no cuenta como solapamiento."""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def rect_modulo(x, y):
    return (x, y, ANCHO_MODULO, ALTO_MODULO)


def modulo_en_lienzo(x, y):
    return 0 <= x and 0 <= y and x + ANCHO_MODULO <= LIENZO_EDITOR_ANCHO and y + ALTO_MODULO <= LIENZO_EDITOR_ALTO


def pares_solapados(modulos):
    """Pares de módulos que se solapan, de una lista de (modulo, x, y).

    Los que están en (0, 0) no cuentan: es "sin posición guardada" y el
    editor los muestra apilados en la esquina hasta que se ubican."""
    ubicados = [(m, x, y) for m, x, y in modulos if not (x == 0 and y == 0)]
    pares = []
    for i, (a, ax, ay) in enumerate(ubicados):
        for b, bx, by in ubicados[i + 1:]:
            if se_solapan(rect_modulo(ax, ay), rect_modulo(bx, by)):
                pares.append((a, b))
    return pares
