"""
fields.py — users
Campos de formulario reutilizables.
"""
from django import forms

from users.validators import validar_correo_udea


class CorreoUdeaField(forms.EmailField):
    """EmailField que además exige el dominio @udea.edu.co exacto."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.validators.append(validar_correo_udea)
