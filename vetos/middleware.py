"""
middleware.py — vetos
Genera los vetos NO_CANCELO pendientes sin depender de un cron externo.

Por qué middleware y no un post_save de Reserva: un no-show es justamente
la reserva que NADIE toca (no se cancela ni se retira), así que su vencimiento
nunca dispara un signal. Revisar en cada request — con el límite de
frecuencia de GenerarVetosNoCanceloService.ejecutar_si_corresponde() — sí
lo detecta, a más tardar VETOS_AUTO_INTERVALO_MINUTOS después de que vence.

Corre ANTES de la vista: si el solicitante vetado está justo pidiendo una
reserva nueva, el veto ya existe cuando se valida su solicitud.
"""
from django.conf import settings

from vetos.services import GenerarVetosNoCanceloService


class VetosAutomaticosMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response
        self.prefijo_static = '/' + settings.STATIC_URL.lstrip('/')

    def __call__(self, request):
        if not request.path.startswith(self.prefijo_static):
            GenerarVetosNoCanceloService.ejecutar_si_corresponde()
        return self.get_response(request)
