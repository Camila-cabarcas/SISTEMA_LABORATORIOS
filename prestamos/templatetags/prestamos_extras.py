"""
prestamos_extras.py — templatetags de la app prestamos
Filtro get_item para acceder a diccionarios (clave -> valor) desde templates.
"""
from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    if not dictionary:
        return None
    return dictionary.get(key)
