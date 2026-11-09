"""
validators.py — users
Correos institucionales: solo se aceptan direcciones @udea.edu.co exactas
(sin subdominios) en los campos de correo que escribe una persona.

Solo valida input nuevo: los registros ya guardados con otro dominio no se
tocan, y las consultas que identifican al dueño de una reserva con el correo
que ya está guardado (Mis Reservas, ver detalle y cancelar como dueño) no
usan este validador, para que las reservas viejas se sigan encontrando.
"""
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

DOMINIO_UDEA = '@udea.edu.co'
MENSAJE_CORREO_UDEA = 'Usa tu correo institucional de la UdeA (@udea.edu.co).'


def validar_correo_udea(valor):
    if not valor:
        return  # vacío lo decide required del campo, no este validador
    correo = valor.strip().lower()
    if (correo.count('@') != 1
            or not correo.endswith(DOMINIO_UDEA)
            or correo.startswith('@')):
        raise ValidationError(MENSAJE_CORREO_UDEA)


def validar_correo_institucional(valor):
    """Para vistas que leen el correo de request.POST sin formulario de
    Django: formato de correo válido (lo que en un formulario hace
    EmailField) + dominio @udea.edu.co. Vacío no es error (lo decide quien
    llama si el campo es obligatorio). Lanza ValidationError con un solo
    mensaje."""
    if not valor:
        return
    try:
        validate_email(valor.strip())
    except ValidationError:
        raise ValidationError(MENSAJE_CORREO_UDEA)
    validar_correo_udea(valor)
