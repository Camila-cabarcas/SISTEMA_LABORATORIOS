from django.db import models


class Rol(models.Model):
    nombre = models.CharField(max_length=100)

    def __str__(self):
        return self.nombre


class Usuario(models.Model):
    nombre = models.CharField(max_length=100)
    correo = models.EmailField(unique=True)
    codigo = models.CharField(max_length=50, unique=True)
    programa = models.CharField(max_length=100)

    rol = models.ForeignKey(
        Rol,
        on_delete=models.CASCADE
    )

    estado = models.BooleanField(default=True)

    def __str__(self):
        return self.nombre