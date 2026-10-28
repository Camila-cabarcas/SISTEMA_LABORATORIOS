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
    var ICONOS = { computador: 'fa-desktop', maquinaria: 'fa-gears' };

    function crear(opciones) {
        var categoria = opciones.categoria || SIN_CATEGORIA;
        var div = document.createElement('div');
        div.className = 'modulo-figura forma-' + (categoria.forma || 'cuadrado');
        div.style.setProperty('--cat-color', categoria.color || SIN_CATEGORIA.color);
        div.title = categoria.nombre;

        if (ICONOS[categoria.forma]) {
            var icono = document.createElement('i');
            icono.className = 'fa-solid ' + ICONOS[categoria.forma] + ' modulo-figura-icono';
            icono.setAttribute('aria-hidden', 'true');
            div.appendChild(icono);
        }

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

    window.ModuloFigura = { crear: crear, cambiarEstado: cambiarEstado, leyenda: leyenda, SIN_CATEGORIA: SIN_CATEGORIA };
})();
