"""
models.py — users
Define los modelos Rol y Usuario (extiende AbstractUser con los campos codigo, programa y rol).
"""
from django.db import models
from django.contrib.auth.hashers import make_password, check_password
from django.contrib.auth.models import AbstractUser


class Rol(models.Model):
    nombre = models.CharField(max_length=100)

    def __str__(self):
        return self.nombre


class ProgramaAcademico(models.Model):
    nombre = models.CharField(max_length=200, unique=True)
    activo = models.BooleanField(default=True)

    class Meta:
        ordering = ['nombre']
        verbose_name = 'Programa académico'
        verbose_name_plural = 'Programas académicos'

    def __str__(self):
        return self.nombre


class Usuario(AbstractUser):
    codigo = models.CharField(max_length=50, unique=True, blank=True)
    programa = models.CharField(max_length=100, blank=True)

    rol = models.ForeignKey(
        Rol,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    # Contraseña separada de la de login, exigida por
    # users.decorators.requiere_contrasena_admin antes de ejecutar acciones
    # críticas (eliminar, desactivar, etc.). Se guarda hasheada igual que
    # la contraseña de login (make_password/check_password de Django), pero
    # es un campo aparte — nunca se deriva ni se compara contra `password`.
    admin_password_hash = models.CharField(max_length=255, blank=True, null=True)

    def set_admin_password(self, raw_password):
        """Guarda la contraseña admin hasheada en la BD."""
        self.admin_password_hash = make_password(raw_password)
        self.save(update_fields=['admin_password_hash'])

    def check_admin_password(self, raw_password):
        """Verifica si la contraseña admin ingresada es correcta."""
        if not self.admin_password_hash:
            return False
        return check_password(raw_password, self.admin_password_hash)

    def tiene_admin_password(self):
        """Indica si el usuario ya configuró una contraseña admin."""
        return bool(self.admin_password_hash)

    def __str__(self):
        return self.username