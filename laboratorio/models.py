from django.db import models


class Laboratorio(models.Model):

    nombre = models.CharField(max_length=100)

    ubicacion = models.CharField(max_length=200)

    encargado = models.ForeignKey(
        'users.Usuario',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    programa = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return self.nombre