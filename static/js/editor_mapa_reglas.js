/*
 * editor_mapa_reglas.js — reglas puras (sin DOM) del editor de mapa.
 *
 * Mismas reglas que el servidor (laboratorio.services.posiciones_mapa y
 * divisiones.guardar_mapa), para decidir en el navegador si una posición de
 * módulo es válida. Las usa static/js/editar_mapa.js (window.EditorMapaReglas)
 * y los tests las cargan en Node (module.exports).
 *
 * Rectángulos: {x, y, w, h}. Tocarse por un borde no es solapar. Un módulo en
 * (0, 0) está "sin posición": ni choca ni lo chocan.
 */
(function (raiz, fabrica) {
    'use strict';
    var api = fabrica();
    if (typeof module === 'object' && module.exports) {
        module.exports = api;
    } else {
        raiz.EditorMapaReglas = api;
    }
})(typeof window !== 'undefined' ? window : globalThis, function () {
    'use strict';

    function seSolapan(a, b) {
        return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
    }

    function contiene(exterior, interior) {
        return interior.x >= exterior.x && interior.y >= exterior.y
            && interior.x + interior.w <= exterior.x + exterior.w
            && interior.y + interior.h <= exterior.y + exterior.h;
    }

    function sinPosicion(x, y) {
        return x === 0 && y === 0;
    }

    function dentroDelLienzo(x, y, modulo, lienzo) {
        return x >= 0 && y >= 0 && x + modulo.w <= lienzo.w && y + modulo.h <= lienzo.h;
    }

    /** ¿Choca un módulo en (x, y) con alguno de `otros` ([{x, y}], ya sin él mismo)? */
    function chocaConModulo(x, y, modulo, otros) {
        if (sinPosicion(x, y)) return false;
        var propio = { x: x, y: y, w: modulo.w, h: modulo.h };
        return otros.some(function (o) {
            return !sinPosicion(o.x, o.y) && seSolapan(propio, { x: o.x, y: o.y, w: modulo.w, h: modulo.h });
        });
    }

    /** ¿Queda a medias dentro de alguna división (corta su borde)? */
    function cortaDivision(x, y, modulo, divisiones) {
        if (sinPosicion(x, y)) return false;
        var propio = { x: x, y: y, w: modulo.w, h: modulo.h };
        return divisiones.some(function (d) { return seSolapan(propio, d) && !contiene(d, propio); });
    }

    /**
     * ¿Puede un módulo de tamaño `modulo` ({w, h}) quedar en (x, y)?
     * No: fuera del lienzo, sobre otro módulo ubicado o cortando el borde de
     * una división.
     */
    function posicionValida(x, y, modulo, lienzo, otros, divisiones) {
        return dentroDelLienzo(x, y, modulo, lienzo)
            && !chocaConModulo(x, y, modulo, otros)
            && !cortaDivision(x, y, modulo, divisiones || []);
    }

    /**
     * Posición con que queda un módulo al soltarlo: la actual si es válida;
     * si no, la que tenía al empezar el arrastre (nunca una con choque).
     */
    function posicionAlSoltar(inicio, actual, esValida) {
        return esValida(actual.x, actual.y) ? actual : inicio;
    }

    return {
        seSolapan: seSolapan,
        contiene: contiene,
        sinPosicion: sinPosicion,
        dentroDelLienzo: dentroDelLienzo,
        chocaConModulo: chocaConModulo,
        cortaDivision: cortaDivision,
        posicionValida: posicionValida,
        posicionAlSoltar: posicionAlSoltar,
    };
});
