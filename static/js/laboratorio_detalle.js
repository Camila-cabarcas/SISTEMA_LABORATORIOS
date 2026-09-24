/*
 * laboratorio_detalle.js — detalle de laboratorio
 * - Click en una fila de insumo: abre #modal-items y carga sus ítems por
 *   fetch (JSON de laboratorio.views.modal_items_insumo).
 * - Al cambiar de pestaña actualiza ?tab= en la URL, para que recargar la
 *   página o volver atrás conserve la pestaña activa.
 */
(function () {
    'use strict';

    var modalEl = document.getElementById('modal-items');
    var tbody = document.getElementById('items-tbody');
    var titulo = document.getElementById('modal-items-titulo');

    function filaMensaje(texto, clase) {
        tbody.replaceChildren();
        var tr = document.createElement('tr');
        var td = document.createElement('td');
        td.colSpan = 3;
        td.className = 'text-center py-3 ' + (clase || 'text-muted');
        td.textContent = texto;
        tr.appendChild(td);
        tbody.appendChild(tr);
    }

    function formatearFecha(iso) {
        if (!iso) return '';
        var fecha = new Date(iso);
        return isNaN(fecha) ? '' : fecha.toLocaleString('es-CO', {
            day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
        });
    }

    function pintarItems(items) {
        if (!items.length) {
            filaMensaje('Este insumo no tiene ítems en el laboratorio.');
            return;
        }
        tbody.replaceChildren();
        items.forEach(function (item) {
            var tr = document.createElement('tr');
            var accion = item.ultima_accion
                ? item.ultima_accion + (item.ultima_fecha ? ' · ' + formatearFecha(item.ultima_fecha) : '')
                : '—';
            [item.codigo, item.estado, accion].forEach(function (valor) {
                var td = document.createElement('td');
                td.textContent = valor;
                tr.appendChild(td);
            });
            tbody.appendChild(tr);
        });
    }

    function cargarItems(url, nombre) {
        titulo.textContent = 'Ítems de ' + nombre;
        filaMensaje('Cargando…');
        bootstrap.Modal.getOrCreateInstance(modalEl).show();

        fetch(url, { headers: { 'Accept': 'application/json' }, credentials: 'same-origin' })
            .then(function (resp) {
                if (!resp.ok) throw new Error('HTTP ' + resp.status);
                return resp.json();
            })
            .then(function (data) { pintarItems(data.items); })
            .catch(function () { filaMensaje('No se pudieron cargar los ítems.', 'text-danger'); });
    }

    if (modalEl && tbody) {
        document.querySelectorAll('.fila-insumo').forEach(function (fila) {
            fila.addEventListener('click', function () {
                cargarItems(fila.dataset.url, fila.dataset.nombre);
            });
        });
    }

    document.querySelectorAll('#tabs-laboratorio [data-bs-toggle="tab"]').forEach(function (enlace) {
        enlace.addEventListener('shown.bs.tab', function () {
            var url = new URL(window.location.href);
            url.searchParams.set('tab', enlace.dataset.tab);
            window.history.replaceState(null, '', url);
        });
    });
})();
