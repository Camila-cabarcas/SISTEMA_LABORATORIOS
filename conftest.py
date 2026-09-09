"""
conftest.py (raíz) — configuración de pytest para toda la suite.

Vive en la raíz (no en tests/) a propósito: sus fixtures autouse deben
aplicar también a los tests que viven dentro de cada app (solicitudes/tests.py,
vetos/tests.py, prestamos/tests.py, ...), no solo a los de tests/.
"""
import pytest


@pytest.fixture(autouse=True)
def _emails_sincronos(monkeypatch):
    """Fuerza el envío de emails a modo síncrono en toda la suite.

    utils.email_tasks.enviar_email_html(async_=True) — el default de todos
    los notificar_* — despacha el correo en un threading.Thread daemon. Con
    el backend locmem de los tests ese hilo no aporta nada (no hay espera de
    red) y sí una condición de carrera: puede escribir en
    django.core.mail.outbox en paralelo con los asserts de otro test, o
    justo después de un mail.outbox.clear(), dejando 2 mensajes donde el
    test espera 1 (así fallaba de forma intermitente
    test_cancelar_reserva_service.py::test_notifica_a_los_encargados_del_laboratorio).

    Reemplazamos la función por una que siempre pasa async_=False, así el
    hilo nunca se crea. Solo se toca el envío de email — ningún otro uso de
    threading — y monkeypatch revierte el parche al terminar cada test.
    """
    import utils.email_tasks as email_tasks
    import utils.notificaciones_email as notificaciones_email

    real = email_tasks.enviar_email_html

    def enviar_sincrono(*args, **kwargs):
        kwargs['async_'] = False
        return real(*args, **kwargs)

    # notificaciones_email hace `from utils.email_tasks import
    # enviar_email_html`, así que tiene su propia referencia al nombre —
    # hay que parchear ambos módulos.
    monkeypatch.setattr(email_tasks, 'enviar_email_html', enviar_sincrono)
    monkeypatch.setattr(notificaciones_email, 'enviar_email_html', enviar_sincrono)
