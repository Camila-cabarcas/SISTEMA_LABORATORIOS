/**
 * flujo_completo.cy.js
 *
 * Flujo E2E completo del Sistema de Laboratorios:
 *   1) Un estudiante crea una solicitud de reserva (pública, sin login) —
 *      su Reserva queda "Aprobada" automáticamente al crearse (ver
 *      SolicitudReserva.crear_reserva()), sin paso de aprobación manual.
 *   2) Un administrador revisa la reserva ya aprobada.
 *   3) Un laboratorista crea el préstamo a partir de la reserva aprobada.
 *   4) El laboratorista inspecciona los ítems al momento de la devolución.
 *   5) El sistema marca el préstamo como "Devuelto" y actualiza el inventario.
 *
 * Los 5 pasos son deliberadamente secuenciales dentro de un solo spec: el
 * paso 2 depende de la solicitud creada en el paso 1, el paso 3 depende de
 * la reserva aprobada en el paso 2, etc. Si un paso falla, los siguientes no
 * tienen datos válidos sobre los que trabajar — tal como pide el requisito
 * "si lo anterior falla, todo falla". El estado compartido (cédula, IDs) se
 * guarda en variables del `describe`.
 *
 * REQUISITOS DE ENTORNO (no se pueden crear vía UI dentro del propio flujo):
 *   - Servidor Django corriendo en http://localhost:8000.
 *   - Datos base ya sembrados con: `python manage.py seed_e2e`
 *     (usuarios e2e_admin / e2e_laboratorista, un laboratorio, un programa
 *     académico activo y un insumo con ítems "Disponible"). Sin esto, los
 *     selects del formulario de estudiante y el de creación de préstamo
 *     estarían vacíos y el flujo no se podría completar por UI.
 *
 * DECISIÓN DE ALCANCE: el formulario de estudiante permite además asignar
 * un módulo/puesto del laboratorio, pero esa sección depende de una llamada
 * AJAX a disponibilidad de módulos con parámetros de fecha/hora. No es
 * necesaria para demostrar el flujo solicitud → reserva → préstamo →
 * inspección → devolución, así que el test desmarca explícitamente
 * "necesita módulo" (el modelo lo trae marcado por defecto) para no
 * depender de esa UI dinámica adicional.
 *
 * LIMITACIÓN DE HORARIO (real, del negocio, no del test): una reserva solo
 * aparece en /reservas/para-prestamo/ cuando su fecha_reserva ya "llegó"
 * (<= ahora) y antes de que venza hora_limite_retiro (fecha_reserva + 30min)
 * — ver reservas/views.py::reservas_para_prestamo. Además el <select> de
 * hora del formulario de estudiante y el horario configurado del
 * laboratorio solo cubren 06:00–18:00. Por eso este spec calcula la hora de
 * inicio como "ahora mismo" (redondeada al múltiplo de 5 más próximo) y
 * espera en el paso 3 lo que haga falta para que el reloj del servidor
 * alcance esa hora. Fuera de la ventana 06:00–18:00 el paso 3 fallará
 * legítimamente, igual que le pasaría a un usuario real: no se puede recoger
 * un préstamo de un laboratorio antes de su horario de apertura.
 */

function horarioDesdeAhora() {
  const ahora = new Date();
  let horas = ahora.getHours();
  let minutos = Math.ceil(ahora.getMinutes() / 5) * 5;
  if (minutos === 60) { minutos = 0; horas += 1; }
  // Los <select> del formulario y el horario del laboratorio cubren 06–18;
  // se deja 2h+ de margen antes del cierre.
  if (horas < 6) { horas = 6; minutos = 0; }
  if (horas > 15) { horas = 15; minutos = 0; }

  // El laboratorio solo abre lunes-viernes (el formulario de estudiante
  // rechaza sábado/domingo con "is-invalid" — ver la validación de fecha en
  // solicitudes/estudiante.html). Si el test corre en fin de semana, se
  // avanza al próximo lunes para que la fecha sea válida.
  const fechaBase = new Date(ahora.getFullYear(), ahora.getMonth(), ahora.getDate());
  const diaSemana = fechaBase.getDay(); // 0 = domingo, 6 = sábado
  if (diaSemana === 6) fechaBase.setDate(fechaBase.getDate() + 2);
  else if (diaSemana === 0) fechaBase.setDate(fechaBase.getDate() + 1);

  const inicioDate = new Date(fechaBase.getFullYear(), fechaBase.getMonth(), fechaBase.getDate(), horas, minutos, 0, 0);
  const yyyy = fechaBase.getFullYear();
  const mm = String(fechaBase.getMonth() + 1).padStart(2, '0');
  const dd = String(fechaBase.getDate()).padStart(2, '0');

  return {
    fecha: `${yyyy}-${mm}-${dd}`,
    inicioH: String(horas).padStart(2, '0'),
    inicioM: String(minutos).padStart(2, '0'),
    finH: String(horas + 2).padStart(2, '0'),
    finM: String(minutos).padStart(2, '0'),
    inicioDate,
  };
}

describe('Flujo completo: solicitud → reserva → préstamo → inspección → devolución', () => {
  let usuarios;
  let laboratorioFixture;

  const cedula = `${Date.now()}`.slice(-9); // cédula única por corrida
  const nombreEstudiante = `E2E Estudiante ${Date.now()}`;
  const horario = horarioDesdeAhora();

  let reservaId;
  let prestamoId;

  before(() => {
    cy.fixture('usuarios').then((data) => { usuarios = data; });
    cy.fixture('laboratorio').then((data) => { laboratorioFixture = data; });
  });

  it('1) Estudiante crea una solicitud de reserva', () => {
    cy.visit('/solicitudes/estudiante/');

    cy.get('#id_nombre').type(nombreEstudiante);
    cy.get('#id_cedula').type(cedula);

    // El programa depende de ProgramaAcademico sembrado; se toma el primero
    // disponible para no acoplar el test a un nombre exacto.
    cy.get('#id_programa option').its('length').should('be.gt', 1);
    cy.get('#id_programa').find('option').eq(1).then((opt) => {
      cy.get('#id_programa').select(opt.val());
    });

    // El laboratorio también se toma dinámicamente; si existe el laboratorio
    // sembrado por seed_e2e se prioriza por nombre, si no, se usa el primero.
    cy.get('#id_laboratorio option').its('length').should('be.gt', 1);
    cy.get('#id_laboratorio').then(($select) => {
      const opcionSembrada = $select.find('option').filter((_, o) => o.text.trim() === laboratorioFixture.nombre);
      const valor = opcionSembrada.length ? opcionSembrada.val() : $select.find('option').eq(1).val();
      cy.wrap($select).select(valor);
    });

    cy.get('#id_fecha_reserva').type(horario.fecha).blur();
    cy.get('#id_fecha_reserva').should('not.have.class', 'is-invalid');

    // El modelo trae "necesita_modulo" en True por defecto; se desmarca para
    // no depender de la UI de selección de módulos (ver nota de alcance arriba).
    cy.get('#id_necesita_modulo').uncheck({ force: true });

    cy.get('#est-hora-inicio-h').select(horario.inicioH);
    cy.get('#est-hora-inicio-m').select(horario.inicioM);
    cy.get('#est-hora-fin-h').select(horario.finH);
    cy.get('#est-hora-fin-m').select(horario.finM);
    cy.get('#horario-error-est').should('have.class', 'd-none');

    // Insumo: se busca el insumo sembrado por seed_e2e y se agrega.
    cy.get('#insumo_buscar').type('Insumo E2E');
    cy.get('#insumo_dropdown', { timeout: 10000 })
      .should('be.visible')
      .contains('.list-group-item', 'Insumo E2E')
      .click();
    cy.get('#insumo_cantidad').clear().type('1');
    cy.get('#agregar_insumo_btn').click();
    cy.get('#insumos_lista').should('be.visible');

    cy.get('#id_observaciones').type('Solicitud creada por la suite E2E de Cypress.');

    cy.screenshot('01-solicitud-formulario-completo');

    cy.get('#solicitud-form').submit();

    // Redirección a la página de éxito.
    cy.url().should('include', '/solicitudes/exitosa/');
    cy.contains('h2', '¡Solicitud enviada!').should('be.visible');

    cy.screenshot('01-solicitud-confirmada');
  });

  it('2) Administrador revisa la reserva ya aprobada automáticamente', () => {
    cy.login(usuarios.admin.username, usuarios.admin.password);

    cy.visit('/reservas/');
    cy.get('#filtro-form input[name="buscar"]').type(cedula);
    cy.get('#filtro-form').contains('button', 'Buscar').click();

    cy.get('table tbody tr').should('have.length.at.least', 1);
    cy.get('table tbody tr').first().within(() => {
      cy.contains('a', 'Ver detalle').click();
    });

    // La reserva nace Aprobada — no hay paso de aprobación manual que hacer.
    cy.verifyStatus('.badge', 'Aprobada');

    cy.url().then((url) => {
      const match = url.match(/\/reservas\/(\d+)\//);
      expect(match, 'URL de detalle de reserva').to.not.be.null;
      reservaId = match[1];
    });

    cy.screenshot('02-reserva-aprobada');
  });

  it('3) Laboratorista crea el préstamo', () => {
    // La reserva solo aparece en para-prestamo cuando su fecha_reserva ya
    // "llegó" — se espera lo que falte para que el reloj del servidor
    // alcance la hora de inicio elegida en el paso 1 (ver nota de horario
    // arriba). Si ya pasó, msRestantes es negativo y no se espera nada.
    const msRestantes = horario.inicioDate.getTime() - Date.now();
    if (msRestantes > 0) {
      cy.wait(msRestantes + 3000);
    }

    cy.login(usuarios.laboratorista.username, usuarios.laboratorista.password);

    cy.visit('/reservas/para-prestamo/');

    cy.contains('td', new RegExp(`^${reservaId}$`))
      .parent('tr')
      .within(() => {
        cy.contains('a', 'Crear préstamo').click();
      });

    cy.url().should('include', `/prestamos/crear/${reservaId}/`);

    // Selecciona el primer ítem disponible para cada insumo de la reserva.
    cy.get('select[name="items"]').each(($select) => {
      cy.wrap($select)
        .find('option')
        .its('length')
        .then((len) => {
          expect(len, 'ítems disponibles para el insumo').to.be.greaterThan(1);
        });
      cy.wrap($select).select(1);
    });

    cy.screenshot('03-prestamo-items-seleccionados');

    cy.contains('button', 'Crear Préstamo').click();

    cy.url().then((url) => {
      const match = url.match(/\/prestamos\/(\d+)\//);
      expect(match, 'URL de detalle de préstamo').to.not.be.null;
      prestamoId = match[1];
    });

    cy.verifyStatus('.badge', 'Activo');
    cy.screenshot('03-prestamo-activo');
  });

  it('4) Laboratorista inspecciona los ítems del préstamo', () => {
    cy.visit(`/prestamos/${prestamoId}/`);
    cy.contains('button', 'Iniciar Inspección').click();

    cy.url().should('include', `/prestamos/${prestamoId}/inspeccionar/`);

    // Marca cada ítem como "Bien" explícitamente.
    cy.get('select.estado-inspeccion-select').each(($select) => {
      cy.wrap($select).select('bien');
    });

    cy.screenshot('04-inspeccion-items-marcados');

    cy.get('button[value="guardar"]').click();

    // El guardado recarga la misma página de inspección.
    cy.url().should('include', `/prestamos/${prestamoId}/inspeccionar/`);
    cy.get('select.estado-inspeccion-select').first().should('have.value', 'bien');

    cy.screenshot('04-inspeccion-guardada');
  });

  it('5) El sistema marca el préstamo como devuelto', () => {
    cy.visit(`/prestamos/${prestamoId}/inspeccionar/`);

    cy.window().then((win) => {
      cy.stub(win, 'confirm').returns(true);
    });

    cy.get('button[value="marcar_devuelto"]').click();

    cy.url().should('include', `/prestamos/${prestamoId}/marcar-devuelto/`);
    cy.contains('button', 'Confirmar').click();

    cy.url().should('include', `/prestamos/${prestamoId}/`);
    cy.verifyStatus('.badge', 'Devuelto');

    // Los ítems marcados "Bien" en la inspección deben quedar "Disponible".
    cy.get('table').contains('td', 'Disponible').should('exist');
    cy.get('table').contains('.badge', 'Bien').should('exist');

    cy.screenshot('05-prestamo-devuelto');
  });
});
