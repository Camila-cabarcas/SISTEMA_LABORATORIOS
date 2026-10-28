/*
 * modulo_figura.js — arma el elemento de un módulo con el color y la forma de
 * su categoría (ver static/css/modulo_figura.css). Lo usan el mapa
 * (laboratorio/mapa.html) y los selectores de módulos de reservas/crear.html,
 * solicitudes/estudiante.html y solicitudes/profesor.html.
 *
 * `categoria` viene de las APIs /laboratorio/<id>/modulos/disponibles[-publica]/
 * o de los data-* del mapa: {nombre, color, forma} o null (= sin categoría).
 */
(function () {
    'use strict';

    var SIN_CATEGORIA = { nombre: 'Sin categoría', color: '#6c757d', forma: 'cuadrado' };
    // Formas que se dibujan con un ícono. Gemelo de
    // templates/laboratorio/partials/icono_categoria.html — mantener iguales.
    var ICONOS_FA = { computador: 'fa-desktop', maquinaria: 'fa-gears' };
    var SVG_NS = 'http://www.w3.org/2000/svg';
    // Mesa: tablero en perspectiva + 4 patas (2 delanteras largas, 2 traseras cortas).
    var MESA = [
        ['path', { d: 'M6 3h20l4 6H2z' }],
        ['rect', { x: 2, y: 9, width: 28, height: 2.5, rx: 0.6 }],
        ['rect', { x: 3, y: 11, width: 2.6, height: 12, rx: 0.8 }],
        ['rect', { x: 26.4, y: 11, width: 2.6, height: 12, rx: 0.8 }],
        ['rect', { x: 8.5, y: 11, width: 2, height: 8, rx: 0.6 }],
        ['rect', { x: 21.5, y: 11, width: 2, height: 8, rx: 0.6 }],
    ];

    /** Elemento del ícono de una forma, o null si la forma no lleva ícono. */
    function icono(forma) {
        if (ICONOS_FA[forma]) {
            var i = document.createElement('i');
            i.className = 'fa-solid ' + ICONOS_FA[forma] + ' modulo-figura-icono';
            i.setAttribute('aria-hidden', 'true');
            return i;
        }
        if (forma === 'mesa') {
            var svg = document.createElementNS(SVG_NS, 'svg');
            svg.setAttribute('class', 'modulo-figura-icono icono-mesa');
            svg.setAttribute('viewBox', '0 0 32 24');
            svg.setAttribute('aria-hidden', 'true');
            svg.setAttribute('focusable', 'false');
            MESA.forEach(function (parte) {
                var el = document.createElementNS(SVG_NS, parte[0]);
                el.setAttribute('fill', 'currentColor');
                Object.keys(parte[1]).forEach(function (k) { el.setAttribute(k, parte[1][k]); });
                svg.appendChild(el);
            });
            return svg;
        }
        return null;
    }

    function crear(opciones) {
        var categoria = opciones.categoria || SIN_CATEGORIA;
        var div = document.createElement('div');
        div.className = 'modulo-figura forma-' + (categoria.forma || 'cuadrado');
        div.style.setProperty('--cat-color', categoria.color || SIN_CATEGORIA.color);
        div.title = categoria.nombre;

        var figuraIcono = icono(categoria.forma);
        if (figuraIcono) div.appendChild(figuraIcono);

        // textContent: los nombres los escribe el usuario, no se interpretan como HTML.
        var nombre = document.createElement('span');
        nombre.className = 'modulo-figura-nombre';
        nombre.textContent = opciones.nombre;
        div.appendChild(nombre);

        (opciones.detalles || []).forEach(function (texto) {
            if (!texto) return;
            var detalle = document.createElement('span');
            detalle.className = 'modulo-figura-detalle';
            detalle.textContent = texto;
            div.appendChild(detalle);
        });

        if (opciones.estadoColor) {
            var punto = document.createElement('span');
            punto.className = 'modulo-estado bg-' + opciones.estadoColor;
            punto.setAttribute('aria-hidden', 'true');
            div.appendChild(punto);
        }
        return div;
    }

    /** Cambia el punto de disponibilidad de un módulo ya dibujado. */
    function cambiarEstado(div, estadoColor) {
        var punto = div.querySelector('.modulo-estado');
        if (punto) punto.className = 'modulo-estado bg-' + estadoColor;
    }

    /** Llena `contenedor` con una figura en miniatura + nombre por categoría. */
    function leyenda(contenedor, categorias, incluirSinCategoria) {
        contenedor.innerHTML = '';
        var lista = (categorias || []).slice();
        if (incluirSinCategoria) lista.push(SIN_CATEGORIA);
        lista.forEach(function (c) {
            var item = document.createElement('span');
            item.className = 'leyenda-categoria';
            var figura = crear({ nombre: '', categoria: c });
            figura.querySelector('.modulo-figura-nombre').remove();
            item.appendChild(figura);
            item.appendChild(document.createTextNode(c.nombre));
            contenedor.appendChild(item);
        });
        contenedor.classList.toggle('d-none', lista.length === 0);
    }

    window.ModuloFigura = {
        crear: crear, icono: icono, cambiarEstado: cambiarEstado, leyenda: leyenda, SIN_CATEGORIA: SIN_CATEGORIA,
    };
})();
