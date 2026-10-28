/*
 * filtro_division_modulos.js — filtro por división (salón) en los
 * selectores de módulos de los formularios de reserva (reservas/crear.html,
 * solicitudes/estudiante.html y solicitudes/profesor.html).
 *
 * Trabaja sobre la respuesta de /laboratorio/<id>/modulos/disponibles[-publica]/:
 * {modulos: [{..., division: {id, nombre} | null}], divisiones: [{id, nombre}]}.
 * El filtro solo oculta/muestra asientos ya dibujados (no los vuelve a
 * crear), así no se pierde la selección de módulos que queden ocultos.
 */
(function () {
    'use strict';

    window.FiltroDivisionModulos = {
        /** Llena el <select> y muestra su contenedor solo si el lab tiene divisiones. */
        poblar: function (select, contenedor, divisiones) {
            var previo = select.value;
            select.innerHTML = '';
            var opciones = [{ valor: '', texto: 'Todas las divisiones' }]
                .concat((divisiones || []).map(function (d) { return { valor: String(d.id), texto: d.nombre }; }))
                .concat([{ valor: 'sin', texto: 'Sin división' }]);
            opciones.forEach(function (o) {
                var opt = document.createElement('option');
                opt.value = o.valor;
                opt.textContent = o.texto;
                select.appendChild(opt);
            });
            var sigueValido = opciones.some(function (o) { return o.valor === previo; });
            select.value = sigueValido ? previo : '';
            contenedor.classList.toggle('d-none', !(divisiones && divisiones.length));
        },

        /** Marca el asiento con su división y le agrega el nombre como texto. */
        etiquetar: function (seat, modulo) {
            seat.dataset.divisionId = modulo.division ? String(modulo.division.id) : '';
            if (!modulo.division) return;
            var etiqueta = document.createElement('span');
            etiqueta.className = 'modulo-division-form';
            etiqueta.textContent = modulo.division.nombre;
            seat.appendChild(etiqueta);
        },

        /** Muestra solo los asientos de la división elegida en el <select>. */
        aplicar: function (select, seats) {
            var valor = select.value;
            Array.prototype.forEach.call(seats, function (seat) {
                var id = seat.dataset.divisionId || '';
                var visible = valor === '' || (valor === 'sin' ? id === '' : id === valor);
                seat.style.display = visible ? '' : 'none';
            });
        },
    };
})();
