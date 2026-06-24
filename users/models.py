"""
models.py — users
Define los modelos Rol y Usuario (extiende AbstractUser con los campos codigo, programa y rol).
"""
from django.db import models
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

    def __str__(self):
        return self.username