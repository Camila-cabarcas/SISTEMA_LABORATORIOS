"""
email_tasks.py — utils
Envío de emails HTML vía SendGrid (ver EMAIL_BACKEND en config/settings.py).
No hay Celery/broker en este proyecto, así que "async" acá es un hilo
aparte para no bloquear la request mientras SendGrid responde — no da
reintentos ni persistencia si el proceso muere a mitad del envío. Para
volumen alto o necesidad de reintentos confiables, esto debería migrar a
una cola de tareas real (Celery + Redis/RabbitMQ).
"""
import logging
import threading

from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


def enviar_email_html(destinatarios, asunto, template_name, contexto=None, async_=True):
    """
    Renderiza `template_name` (debe extender emails/base_email.html) con
    `contexto` y lo envía por SendGrid.

    Args:
        destinatarios: un email (str) o lista de emails.
        asunto: subject del correo.
        template_name: ruta del template HTML, ej. 'emails/devolucion_completada.html'.
        contexto: dict para el template (default: {}).
        async_: si True (default), el envío corre en un hilo aparte y esta
            función retorna de inmediato sin esperar la respuesta de
            SendGrid; cualquier error queda solo en el log. Si False, envía
            sincrónicamente y deja que la excepción se propague — para
            comandos/tests donde sí importa saber si realmente se envió.
    """
    if isinstance(destinatarios, str):
        destinatarios = [destinatarios]

    html = render_to_string(template_name, contexto or {})
    texto_plano = strip_tags(html)

    def _construir_y_enviar():
        email = EmailMultiAlternatives(asunto, texto_plano, to=destinatarios)
        email.attach_alternative(html, 'text/html')
        email.send()

    if not async_:
        _construir_y_enviar()
        return

    def _enviar_en_hilo():
        try:
            _construir_y_enviar()
            logger.info(
                'enviar_email_html | enviado | asunto=%s | destinatarios=%s',
                asunto, destinatarios,
            )
        except Exception:
            logger.exception(
                'enviar_email_html | error enviando | asunto=%s | destinatarios=%s',
                asunto, destinatarios,
            )

    threading.Thread(target=_enviar_en_hilo, daemon=True).start()
