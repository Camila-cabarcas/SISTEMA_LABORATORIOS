"""
settings_test.py — SOLO PARA PRUEBAS, NUNCA EN PRODUCCIÓN.

Hereda todo de config/settings.py y solo cambia lo que acelera la suite.
pytest lo carga desde pytest.ini (DJANGO_SETTINGS_MODULE).
"""
from .settings import *  # noqa: F401,F403

# Solo para pruebas, nunca en producción: MD5 es inseguro pero muy rápido.
# Los hashers por defecto (PBKDF2) son lentos a propósito y cada
# create_user / login / check_password de los tests paga ese costo.
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
