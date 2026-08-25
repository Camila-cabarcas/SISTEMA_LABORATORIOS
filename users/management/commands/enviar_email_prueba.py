"""
enviar_email_prueba.py — users
Comando de ejemplo/diagnóstico para verificar que la configuración de
SendGrid (config/settings.py) realmente puede enviar correo. Envía
sincrónicamente (async_=False) a propósito, para que cualquier error de
SendGrid (API key inválida, sender no verificado, etc.) se vea en la
terminal en vez de perderse en un hilo de fondo.
"""
from django.core.management.base import BaseCommand, CommandError

from utils.email_tasks import enviar_email_html


class Command(BaseCommand):
    help = 'Envía un email de prueba vía SendGrid para verificar la configuración.'

    def add_arguments(self, parser):
        parser.add_argument('destinatario', type=str, help='Email al que se envía la prueba.')
        parser.add_argument('--nombre', type=str, default='', help='Nombre para personalizar el saludo.')

    def handle(self, *args, **options):
        destinatario = options['destinatario']
        nombre = options['nombre']

        self.stdout.write(f'Enviando email de prueba a {destinatario}...')

        try:
            enviar_email_html(
                destinatarios=destinatario,
                asunto='Email de prueba — Sistema de Laboratorios',
                template_name='emails/prueba.html',
                contexto={'nombre': nombre},
                async_=False,
            )
        except Exception as e:
            raise CommandError(f'No se pudo enviar el email: {e}')

        self.stdout.write(self.style.SUCCESS(f'Email enviado correctamente a {destinatario}.'))
