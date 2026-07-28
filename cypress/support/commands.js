/**
 * commands.js
 * Comandos custom reutilizados por la suite E2E del Sistema de Laboratorios.
 */

// cy.login(username, password)
// El login del sistema es por username (AuthenticationForm de Django estándar,
// campos #id_username / #id_password) — el modelo Usuario no tiene login por
// email, por eso el comando recibe "username" y no "email".
Cypress.Commands.add('login', (username, password) => {
  cy.visit('/login/');
  cy.get('#id_username').clear().type(username);
  cy.get('#id_password').clear().type(password, { log: false });
  cy.contains('button', 'Entrar').click();
  cy.url().should('not.include', '/login/');
});

// cy.fillForm(formSelector, data)
// Llena un formulario a partir de un objeto { nombreDeCampo: valor }.
// Detecta automáticamente si el campo es un <select>, checkbox, radio o
// input de texto y actúa en consecuencia.
Cypress.Commands.add('fillForm', (formSelector, data) => {
  Object.entries(data).forEach(([field, value]) => {
    cy.get(`${formSelector} [name="${field}"]`).then(($el) => {
      const tag = $el.prop('tagName').toLowerCase();
      const type = ($el.attr('type') || '').toLowerCase();

      if (tag === 'select') {
        cy.wrap($el).select(String(value));
      } else if (type === 'checkbox') {
        if (value) {
          cy.wrap($el).check();
        } else {
          cy.wrap($el).uncheck();
        }
      } else if (type === 'radio') {
        cy.wrap($el).check(String(value));
      } else {
        cy.wrap($el).clear().type(String(value));
      }
    });
  });
});

// cy.verifyStatus(elementSelector, status)
// Verifica que el badge/elemento de estado muestre el texto esperado
// (ej. cy.verifyStatus('.badge', 'Aprobada')).
Cypress.Commands.add('verifyStatus', (elementSelector, status) => {
  cy.get(elementSelector).should('contain.text', status);
});
