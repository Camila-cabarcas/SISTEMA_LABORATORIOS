/*
 * editar_mapa.js — editor del mapa de laboratorio
 * - Módulos: clic = seleccionar (panel lateral con nombre, categoría y
 *   posición X/Y). Arrastre con pointer events (mouse y táctil): el módulo
 *   conserva el punto por donde se agarró y no puede salir del lienzo.
 * - Sin solapamiento: mientras se arrastra, el módulo puede pasar por encima
 *   de otros (se marca en rojo y va por encima). Al soltar, si la posición
 *   choca con otro módulo o corta el borde de una división (queda a medias
 *   dentro), vuelve a donde empezó el arrastre. Las reglas están en
 *   static/js/editor_mapa_reglas.js (mismas que el servidor); los módulos en
 *   (0, 0) son "sin posición" y no cuentan para los choques.
 * - Divisiones (salones, opcionales, máx. data-max-divisiones): se agregan,
 *   se mueven desde su barra, se redimensionan desde la esquina, se renombran
 *   en la misma barra y se eliminan. Mover una división no mueve sus módulos.
 * - Tamaños (módulo, mínimos de división) llegan del servidor en data-* del
 *   lienzo; el lienzo tiene tamaño fijo (también del servidor, en el CSS).
 * - "Guardar" envía posiciones + categoría de cada módulo + el conjunto
 *   completo de divisiones (todo o nada).
 */
(function () {
    'use strict';

    var canvas = document.getElementById('editor-canvas');
    var btnGuardar = document.getElementById('btn-guardar');
    var estado = document.getElementById('estado-guardado');
    if (!canvas || !btnGuardar) return;

    var datos = canvas.dataset;
    var ANCHO_MODULO = parseInt(datos.anchoModulo, 10);
    var ALTO_MODULO = parseInt(datos.altoModulo, 10);
    var ANCHO_MIN = parseInt(datos.divisionAnchoMin, 10);
    var ALTO_MIN = parseInt(datos.divisionAltoMin, 10);
    var MAX_DIVISIONES = parseInt(datos.maxDivisiones, 10);

    var btnAgregar = document.getElementById('btn-agregar-division');
    var contador = document.getElementById('contador-divisiones');
    var plantilla = document.getElementById('plantilla-division');

    var panel = {
        vacio: document.getElementById('panel-vacio'),
        detalle: document.getElementById('panel-detalle'),
        nombre: document.getElementById('panel-nombre'),
        categoria: document.getElementById('panel-categoria'),
        x: document.getElementById('panel-x'),
        y: document.getElementById('panel-y'),
        aviso: document.getElementById('panel-aviso'),
        division: document.getElementById('panel-division'),
        divisionNombre: document.getElementById('panel-division-nombre'),
        divisionPosicion: document.getElementById('panel-division-posicion'),
        divisionTamano: document.getElementById('panel-division-tamano'),
    };
    panel.x.max = canvas.clientWidth - ANCHO_MODULO;
    panel.y.max = canvas.clientHeight - ALTO_MODULO;

    var TEXTO_GUARDAR = btnGuardar.textContent.trim();
    var hayCambios = false;
    var seleccionado = null;          // módulo seleccionado
    var divisionSeleccionada = null;  // o división seleccionada (nunca ambos)

    function marcarCambios() {
        hayCambios = true;
        btnGuardar.disabled = false;
        btnGuardar.textContent = TEXTO_GUARDAR + ' (sin guardar)';
        estado.textContent = '';
    }

    function limitar(valor, minimo, maximo) {
        return Math.max(minimo, Math.min(Math.round(valor), Math.max(minimo, maximo)));
    }

    function num(el, clave) { return parseInt(el.dataset[clave], 10) || 0; }

    function modulos() { return Array.prototype.slice.call(canvas.querySelectorAll('.modulo-item')); }
    function divisiones() { return Array.prototype.slice.call(canvas.querySelectorAll('.division-item')); }

    // ── Geometría: static/js/editor_mapa_reglas.js (mismas reglas que el servidor) ──
    var reglas = window.EditorMapaReglas;
    var TAM_MODULO = { w: ANCHO_MODULO, h: ALTO_MODULO };

    function rectDivision(d) {
        return { x: num(d, 'x'), y: num(d, 'y'), w: num(d, 'ancho'), h: num(d, 'alto') };
    }
    function sinPosicion(x, y) { return reglas.sinPosicion(x, y); }

    /** ¿Puede `modulo` quedar en (x, y)? Fuera del lienzo, sobre otro módulo
     *  ubicado o cortando el borde de una división: no. (0, 0) = sin posición. */
    function posicionValida(modulo, x, y) {
        var otros = modulos()
            .filter(function (otro) { return otro !== modulo; })
            .map(function (otro) { return { x: num(otro, 'x'), y: num(otro, 'y') }; });
        return reglas.posicionValida(
            x, y, TAM_MODULO, { w: canvas.clientWidth, h: canvas.clientHeight },
            otros, divisiones().map(rectDivision)
        );
    }

    function moverModulo(modulo, x, y) {
        modulo.style.left = x + 'px';
        modulo.style.top = y + 'px';
        modulo.dataset.x = x;
        modulo.dataset.y = y;
        if (modulo === seleccionado) {
            panel.x.value = x;
            panel.y.value = y;
        }
    }

    function marcarInvalido(modulo, invalido) {
        modulo.classList.toggle('invalido', invalido);
        if (modulo === seleccionado) panel.aviso.classList.toggle('d-none', !invalido);
    }

    // Mismo criterio que laboratorio.services.divisiones.division_para:
    // la división que contiene el centro del módulo.
    function divisionBajo(modulo) {
        var x = num(modulo, 'x'), y = num(modulo, 'y');
        if (sinPosicion(x, y)) return null;
        var cx = x + ANCHO_MODULO / 2, cy = y + ALTO_MODULO / 2;
        var lista = divisiones();
        for (var i = 0; i < lista.length; i++) {
            var r = rectDivision(lista[i]);
            if (cx >= r.x && cx < r.x + r.w && cy >= r.y && cy < r.y + r.h) return lista[i];
        }
        return null;
    }

    // Vista previa de la división de cada módulo (el servidor decide al guardar).
    function actualizarEtiquetas() {
        modulos().forEach(function (modulo) {
            var etiqueta = modulo.querySelector('.modulo-item-division');
            if (!etiqueta) return;
            var division = divisionBajo(modulo);
            etiqueta.textContent = division ? division.querySelector('.division-nombre').value : '';
        });
    }

    function actualizarContador() {
        var n = divisiones().length;
        contador.textContent = n;
        btnAgregar.disabled = n >= MAX_DIVISIONES;
    }

    // ── Selección y panel ─────────────────────────────────────────────
    function quitarSeleccionDivision() {
        if (divisionSeleccionada) divisionSeleccionada.classList.remove('seleccionada');
        divisionSeleccionada = null;
        panel.division.classList.add('d-none');
    }

    function mostrarDivisionEnPanel() {
        var d = divisionSeleccionada;
        if (!d) return;
        panel.divisionNombre.textContent = d.querySelector('.division-nombre').value.trim() || '(sin nombre)';
        panel.divisionPosicion.textContent = 'X ' + num(d, 'x') + ', Y ' + num(d, 'y');
        panel.divisionTamano.textContent = num(d, 'ancho') + ' × ' + num(d, 'alto') + ' px';
    }

    function seleccionarDivision(division) {
        if (seleccionado) seleccionado.classList.remove('seleccionado');
        seleccionado = null;
        panel.detalle.classList.add('d-none');
        if (divisionSeleccionada && divisionSeleccionada !== division) {
            divisionSeleccionada.classList.remove('seleccionada');
        }
        divisionSeleccionada = division;
        division.classList.add('seleccionada');
        panel.vacio.classList.add('d-none');
        panel.division.classList.remove('d-none');
        mostrarDivisionEnPanel();
    }

    function seleccionar(modulo) {
        quitarSeleccionDivision();
        if (seleccionado) seleccionado.classList.remove('seleccionado');
        seleccionado = modulo;
        panel.vacio.classList.toggle('d-none', !!modulo);
        panel.detalle.classList.toggle('d-none', !modulo);
        if (!modulo) return;
        modulo.classList.add('seleccionado');
        panel.nombre.textContent = modulo.dataset.nombre;
        panel.categoria.value = modulo.dataset.categoriaId || '';
        panel.x.value = num(modulo, 'x');
        panel.y.value = num(modulo, 'y');
        panel.x.classList.remove('is-invalid');
        panel.y.classList.remove('is-invalid');
        panel.aviso.classList.add('d-none');
    }

    canvas.addEventListener('pointerdown', function (e) {
        if (e.target === canvas) seleccionar(null);  // clic en el fondo
    });

    // Aviso de módulos fuera del lienzo: seleccionarlos para moverlos con X/Y.
    document.querySelectorAll('[data-seleccionar-modulo]').forEach(function (boton) {
        boton.addEventListener('click', function () {
            var modulo = canvas.querySelector('.modulo-item[data-id="' + boton.dataset.seleccionarModulo + '"]');
            if (!modulo) return;
            seleccionar(modulo);
            panel.x.focus();
        });
    });

    function moverDesdePanel() {
        if (!seleccionado) return;
        var x = parseInt(panel.x.value, 10);
        var y = parseInt(panel.y.value, 10);
        var valida = !isNaN(x) && !isNaN(y) && posicionValida(seleccionado, x, y);
        panel.x.classList.toggle('is-invalid', !valida);
        panel.y.classList.toggle('is-invalid', !valida);
        marcarInvalido(seleccionado, !valida);
        if (!valida) return;  // se queda en la última posición válida
        if (x === num(seleccionado, 'x') && y === num(seleccionado, 'y')) return;
        moverModulo(seleccionado, x, y);
        actualizarEtiquetas();
        marcarCambios();
    }
    panel.x.addEventListener('input', moverDesdePanel);
    panel.y.addEventListener('input', moverDesdePanel);
    // Al salir del campo, si quedó un valor inválido se vuelve a mostrar el válido.
    [panel.x, panel.y].forEach(function (campo) {
        campo.addEventListener('change', function () {
            if (!seleccionado || !campo.classList.contains('is-invalid')) return;
            panel.x.value = num(seleccionado, 'x');
            panel.y.value = num(seleccionado, 'y');
            panel.x.classList.remove('is-invalid');
            panel.y.classList.remove('is-invalid');
            marcarInvalido(seleccionado, false);
        });
    });

    // Cambiar la categoría redibuja la figura y el color al instante.
    var COLOR_SIN_CATEGORIA = window.ModuloFigura.SIN_CATEGORIA.color;
    panel.categoria.addEventListener('change', function () {
        if (!seleccionado) return;
        var opcion = panel.categoria.selectedOptions[0];
        var id = panel.categoria.value;
        var forma = id ? opcion.dataset.forma : 'cuadrado';
        var color = id ? opcion.dataset.color : COLOR_SIN_CATEGORIA;

        seleccionado.dataset.categoriaId = id;
        var figura = seleccionado.querySelector('.modulo-figura');
        figura.className = 'modulo-figura forma-' + forma;
        figura.style.setProperty('--cat-color', color);
        figura.title = id ? opcion.textContent.trim() : 'Sin categoría';
        var viejo = figura.querySelector('.modulo-figura-icono');
        if (viejo) viejo.remove();
        var icono = window.ModuloFigura.icono(forma);
        if (icono) figura.insertBefore(icono, figura.firstChild);
        marcarCambios();
    });

    // ── Arrastre ──────────────────────────────────────────────────────
    function puntoEnLienzo(e) {
        var rect = canvas.getBoundingClientRect();
        return {
            x: e.clientX - rect.left - canvas.clientLeft,
            y: e.clientY - rect.top - canvas.clientTop,
        };
    }

    /**
     * Arrastre genérico, siempre dentro del lienzo. `mover(x, y)` aplica cada
     * posición; `alEmpezar`, `alMover` y `alSoltar` son ganchos opcionales.
     */
    function arrastrable(elemento, asa, opciones) {
        var offsetX = 0;
        var offsetY = 0;

        asa.addEventListener('pointerdown', function (e) {
            if (e.button !== 0 || e.target.closest('input, button')) return;
            var rect = elemento.getBoundingClientRect();
            offsetX = e.clientX - rect.left;
            offsetY = e.clientY - rect.top;
            asa.setPointerCapture(e.pointerId);
            elemento.classList.add('arrastrando');
            if (opciones.alEmpezar) opciones.alEmpezar();
            e.preventDefault();
        });

        asa.addEventListener('pointermove', function (e) {
            if (!asa.hasPointerCapture(e.pointerId)) return;
            var p = puntoEnLienzo(e);
            var x = limitar(p.x - offsetX, 0, canvas.clientWidth - elemento.offsetWidth);
            var y = limitar(p.y - offsetY, 0, canvas.clientHeight - elemento.offsetHeight);
            if (x === num(elemento, 'x') && y === num(elemento, 'y')) return;
            opciones.mover(x, y);
            if (opciones.alMover) opciones.alMover();
            marcarCambios();
        });

        function soltar(e) {
            if (asa.hasPointerCapture(e.pointerId)) asa.releasePointerCapture(e.pointerId);
            elemento.classList.remove('arrastrando');
            canvas.querySelectorAll('.division-item.destino').forEach(function (d) {
                d.classList.remove('destino');
            });
            if (opciones.alSoltar) opciones.alSoltar();
            actualizarEtiquetas();
        }
        asa.addEventListener('pointerup', soltar);
        asa.addEventListener('pointercancel', soltar);
    }

    // ── Módulos ───────────────────────────────────────────────────────
    // Durante el arrastre el módulo puede pasar por encima de otros: no se
    // bloquea; si la posición actual no es válida se marca en rojo (y va por
    // encima de los demás: .arrastrando). Al soltar, si la posición choca,
    // vuelve a donde empezó el arrastre — nunca se acepta una con choque.
    // Sigue sin poder salir del lienzo (arrastrable limita x/y al lienzo).
    modulos().forEach(function (modulo) {
        var inicio = null;
        arrastrable(modulo, modulo, {
            alEmpezar: function () {
                seleccionar(modulo);
                inicio = { x: num(modulo, 'x'), y: num(modulo, 'y') };
            },
            mover: function (x, y) {
                moverModulo(modulo, x, y);
                marcarInvalido(modulo, !posicionValida(modulo, x, y));
            },
            alMover: function () {
                var destino = divisionBajo(modulo);
                divisiones().forEach(function (d) { d.classList.toggle('destino', d === destino); });
            },
            alSoltar: function () {
                if (!inicio) return;
                var final = reglas.posicionAlSoltar(
                    inicio, { x: num(modulo, 'x'), y: num(modulo, 'y') },
                    function (x, y) { return posicionValida(modulo, x, y); }
                );
                moverModulo(modulo, final.x, final.y);
                marcarInvalido(modulo, false);
                modulo.dataset.ultimoSoltar = final === inicio ? 'revertido' : 'aceptado';
                inicio = null;
            },
        });
    });

    // ── Divisiones ────────────────────────────────────────────────────
    function prepararDivision(division) {
        var barra = division.querySelector('.division-barra');
        // Seleccionar desde cualquier punto de la barra (también el nombre o ✕).
        barra.addEventListener('pointerdown', function () { seleccionarDivision(division); });
        arrastrable(division, barra, {
            mover: function (x, y) {
                division.style.left = x + 'px';
                division.style.top = y + 'px';
                division.dataset.x = x;
                division.dataset.y = y;
            },
            alMover: function () { if (division === divisionSeleccionada) mostrarDivisionEnPanel(); },
        });

        var asaTamano = division.querySelector('.division-redimensionar');
        asaTamano.addEventListener('pointerdown', function (e) {
            if (e.button !== 0) return;
            seleccionarDivision(division);
            asaTamano.setPointerCapture(e.pointerId);
            e.preventDefault();
            e.stopPropagation();
        });
        asaTamano.addEventListener('pointermove', function (e) {
            if (!asaTamano.hasPointerCapture(e.pointerId)) return;
            var p = puntoEnLienzo(e);
            var x = num(division, 'x');
            var y = num(division, 'y');
            // No puede salir del lienzo: el tope es el borde derecho/inferior.
            var ancho = limitar(p.x - x, ANCHO_MIN, canvas.clientWidth - x);
            var alto = limitar(p.y - y, ALTO_MIN, canvas.clientHeight - y);
            if (ancho === num(division, 'ancho') && alto === num(division, 'alto')) return;
            division.style.width = ancho + 'px';
            division.style.height = alto + 'px';
            division.dataset.ancho = ancho;
            division.dataset.alto = alto;
            if (division === divisionSeleccionada) mostrarDivisionEnPanel();
            marcarCambios();
        });
        function soltarTamano(e) {
            if (asaTamano.hasPointerCapture(e.pointerId)) asaTamano.releasePointerCapture(e.pointerId);
            actualizarEtiquetas();
        }
        asaTamano.addEventListener('pointerup', soltarTamano);
        asaTamano.addEventListener('pointercancel', soltarTamano);

        division.querySelector('.division-nombre').addEventListener('input', function () {
            if (division === divisionSeleccionada) mostrarDivisionEnPanel();
            marcarCambios();
            actualizarEtiquetas();
        });

        division.querySelector('.division-eliminar').addEventListener('click', function () {
            if (division === divisionSeleccionada) {
                quitarSeleccionDivision();
                panel.vacio.classList.remove('d-none');
            }
            division.remove();
            actualizarContador();
            actualizarEtiquetas();
            marcarCambios();
        });
    }

    divisiones().forEach(prepararDivision);

    btnAgregar.addEventListener('click', function () {
        var n = divisiones().length;
        if (n >= MAX_DIVISIONES) return;

        var nombresUsados = divisiones().map(function (d) {
            return d.querySelector('.division-nombre').value.trim().toLowerCase();
        });
        var numero = n + 1;
        while (nombresUsados.indexOf(('Salón ' + numero).toLowerCase()) !== -1) numero++;

        var division = plantilla.content.firstElementChild.cloneNode(true);
        var ancho = Math.min(300, canvas.clientWidth);
        var alto = Math.min(200, canvas.clientHeight);
        var x = limitar(20 + n * 30, 0, canvas.clientWidth - ancho);
        var y = limitar(20 + n * 30, 0, canvas.clientHeight - alto);
        Object.assign(division.dataset, { x: x, y: y, ancho: ancho, alto: alto });
        Object.assign(division.style, {
            left: x + 'px', top: y + 'px', width: ancho + 'px', height: alto + 'px',
        });
        division.querySelector('.division-nombre').value = 'Salón ' + numero;
        // Antes que los módulos en el DOM: quedan por debajo (también por z-index).
        canvas.insertBefore(division, canvas.firstChild);
        prepararDivision(division);
        actualizarContador();
        actualizarEtiquetas();
        marcarCambios();
        division.querySelector('.division-nombre').select();
    });

    // ── Guardar ───────────────────────────────────────────────────────
    btnGuardar.addEventListener('click', function () {
        var listaModulos = modulos().map(function (item) {
            return {
                id: parseInt(item.dataset.id, 10),
                x: num(item, 'x'),
                y: num(item, 'y'),
                categoria: item.dataset.categoriaId ? parseInt(item.dataset.categoriaId, 10) : null,
            };
        });
        var listaDivisiones = divisiones().map(function (d) {
            return {
                id: d.dataset.id ? parseInt(d.dataset.id, 10) : null,
                nombre: d.querySelector('.division-nombre').value.trim(),
                x: num(d, 'x'),
                y: num(d, 'y'),
                ancho: num(d, 'ancho'),
                alto: num(d, 'alto'),
            };
        });

        btnGuardar.disabled = true;
        estado.className = 'text-muted small';
        estado.textContent = 'Guardando…';

        fetch(datos.guardarUrl, {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': datos.csrf,
            },
            body: JSON.stringify({ modulos: listaModulos, divisiones: listaDivisiones }),
        })
            .then(function (resp) {
                return resp.json().catch(function () { return {}; }).then(function (data) {
                    if (!resp.ok || data.status !== 'ok') {
                        throw new Error(data.error || ('HTTP ' + resp.status));
                    }
                    return data;
                });
            })
            .then(function () {
                hayCambios = false;
                estado.className = 'text-success small';
                estado.textContent = '✅ Mapa guardado correctamente. Volviendo al mapa…';
                window.location.href = datos.mapaUrl;
            })
            .catch(function (err) {
                btnGuardar.disabled = false;
                estado.className = 'text-danger small';
                estado.textContent = 'No se pudo guardar: ' + err.message;
            });
    });

    // Aviso si se intenta salir con cambios sin guardar.
    window.addEventListener('beforeunload', function (e) {
        if (!hayCambios) return;
        e.preventDefault();
        e.returnValue = '';
    });

    actualizarContador();
})();
