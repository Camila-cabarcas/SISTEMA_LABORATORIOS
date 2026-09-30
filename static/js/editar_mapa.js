/*
 * editar_mapa.js — editor del mapa de laboratorio (drag & drop de módulos)
 * - Arrastre con pointer events (mouse y táctil): el módulo conserva el
 *   punto por donde se agarró y no puede salirse del lienzo.
 * - "Guardar" envía todas las posiciones a laboratorio.views.guardar_mapa_laboratorio
 *   y, si sale bien, vuelve al mapa del laboratorio.
 */
(function () {
    'use strict';

    var canvas = document.getElementById('editor-canvas');
    var btnGuardar = document.getElementById('btn-guardar');
    var estado = document.getElementById('estado-guardado');
    if (!canvas || !btnGuardar) return;

    var TEXTO_GUARDAR = btnGuardar.textContent.trim();
    var hayCambios = false;

    function marcarCambios() {
        hayCambios = true;
        btnGuardar.disabled = false;
        btnGuardar.textContent = TEXTO_GUARDAR + ' (sin guardar)';
        estado.textContent = '';
    }

    function limitar(valor, maximo) {
        return Math.max(0, Math.min(Math.round(valor), Math.max(0, maximo)));
    }

    canvas.querySelectorAll('.modulo-item').forEach(function (item) {
        var offsetX = 0;
        var offsetY = 0;

        item.addEventListener('pointerdown', function (e) {
            if (e.button !== 0) return;
            var rect = item.getBoundingClientRect();
            offsetX = e.clientX - rect.left;
            offsetY = e.clientY - rect.top;
            item.setPointerCapture(e.pointerId);
            item.classList.add('arrastrando');
            e.preventDefault();
        });

        item.addEventListener('pointermove', function (e) {
            if (!item.hasPointerCapture(e.pointerId)) return;
            var rect = canvas.getBoundingClientRect();
            // clientLeft/Top: descuenta el borde del lienzo.
            var x = limitar(e.clientX - rect.left - canvas.clientLeft - offsetX,
                            canvas.clientWidth - item.offsetWidth);
            var y = limitar(e.clientY - rect.top - canvas.clientTop - offsetY,
                            canvas.clientHeight - item.offsetHeight);
            if (String(x) === item.dataset.x && String(y) === item.dataset.y) return;
            item.style.left = x + 'px';
            item.style.top = y + 'px';
            item.dataset.x = x;
            item.dataset.y = y;
            marcarCambios();
        });

        function soltar(e) {
            if (item.hasPointerCapture(e.pointerId)) item.releasePointerCapture(e.pointerId);
            item.classList.remove('arrastrando');
        }
        item.addEventListener('pointerup', soltar);
        item.addEventListener('pointercancel', soltar);
    });

    btnGuardar.addEventListener('click', function () {
        var modulos = Array.prototype.map.call(canvas.querySelectorAll('.modulo-item'), function (item) {
            return {
                id: parseInt(item.dataset.id, 10),
                x: parseInt(item.dataset.x, 10) || 0,
                y: parseInt(item.dataset.y, 10) || 0,
            };
        });

        btnGuardar.disabled = true;
        estado.className = 'text-muted small';
        estado.textContent = 'Guardando…';

        fetch(canvas.dataset.guardarUrl, {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': canvas.dataset.csrf,
            },
            body: JSON.stringify({ modulos: modulos }),
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
                window.location.href = canvas.dataset.mapaUrl;
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
})();
