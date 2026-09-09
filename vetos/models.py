"""
models.py — vetos
Define Veto: una sanción temporal que bloquea a un solicitante (estudiante o
profesor) para crear nuevas reservas, como consecuencia de una infracción en
un préstamo o reserva.

Identificación del sancionado
-----------------------------
Este sistema no tiene login de estudiante (ver
solicitudes.services.mis_reservas_service): un estudiante se identifica por
`cedula`, un profesor por su cuenta `Usuario`. Un Veto guarda ambos cuando
puede — `cedula` siempre que se conozca, y `usuario` si el sancionado tiene
cuenta — y el bloqueo (ver vetos.services.vetos_vigentes_para) casa por
cédula o por usuario, mismo criterio que
SolicitudReserva.limite_pendientes_alcanzado y Prestamo.tiene_prestamo_activo.

Vigencia
--------
Un Veto bloquea mientras `estado == ACTIVO` y aún no llega `fecha_fin`
(`fecha_fin is None` = bloqueo indefinido "hasta reponer/pagar", para
DANO y FALTA_INSUMO). Resolverlo (RESUELTO / PAGADO) lo desactiva aunque la
fecha todavía no haya pasado.
"""
from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from users.models import Usuario


class Veto(models.Model):
    # ── Tipos de infracción ────────────────────────────────────────────────
    NO_CANCELO = 'NO_CANCELO'
    RETRASO = 'RETRASO'
    DANO = 'DANO'
    FALTA_INSUMO = 'FALTA_INSUMO'

    TIPO_CHOICES = [
        (NO_CANCELO, 'No canceló y dejó pasar el préstamo'),
        (RETRASO, 'Retraso en la devolución'),
        (DANO, 'Insumo dañado o extraviado'),
        (FALTA_INSUMO, 'Falta de insumo'),
    ]

    # Tipos que un Laboratorista puede levantar por su cuenta; el resto
    # (DANO, FALTA_INSUMO) solo un Administrador, y solo tras verificar la
    # reposición/pago.
    TIPOS_REMOVIBLES_POR_LABORATORISTA = (NO_CANCELO, RETRASO)

    # ── Estado del veto ───────────────────────────────────────────────────
    ACTIVO = 'ACTIVO'
    RESUELTO = 'RESUELTO'
    PAGADO = 'PAGADO'

    ESTADO_CHOICES = [
        (ACTIVO, 'Activo'),
        (RESUELTO, 'Resuelto'),
        (PAGADO, 'Pagado / repuesto'),
    ]

    # Castigo base para NO_CANCELO, y castigo agravado cuando el mismo
    # solicitante acumula ACUMULACION_NO_CANCELO infracciones de ese tipo.
    DIAS_NO_CANCELO = 1
    DIAS_NO_CANCELO_AGRAVADO = 7
    ACUMULACION_NO_CANCELO = 3

    # RETRASO: días de bloqueo por cada día de atraso en la devolución.
    DIAS_BLOQUEO_POR_DIA_ATRASO = 2

    # ── Identificación del sancionado ────────────────────────────────────
    cedula = models.CharField(max_length=50, blank=True, default='', db_index=True)
    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='vetos',
    )

    # ── Infracción ──────────────────────────────────────────────────────
    tipo = models.CharField(max_length=20, choices=TIPO_CHOICES)
    estado = models.CharField(max_length=10, choices=ESTADO_CHOICES, default=ACTIVO)

    fecha_inicio = models.DateField(default=date.today)
    # None = bloqueo indefinido hasta reponer/pagar (DANO, FALTA_INSUMO).
    fecha_fin = models.DateField(null=True, blank=True)

    motivo = models.TextField(blank=True, default='')

    # Reserva / Préstamo que originó la sanción (informativo — SET_NULL para
    # no perder el historial de vetos si el préstamo se borra).
    reserva = models.ForeignKey(
        'reservas.Reserva',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='vetos',
    )
    prestamo = models.ForeignKey(
        'prestamos.Prestamo',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='vetos',
    )

    creado_por = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='vetos_creados',
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    resuelto_por = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='vetos_resueltos',
    )
    fecha_resolucion = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-fecha_creacion']
        verbose_name = 'Veto'
        verbose_name_plural = 'Vetos'

    def __str__(self):
        quien = self.usuario.username if self.usuario_id else (self.cedula or 'desconocido')
        return f"Veto {self.get_tipo_display()} — {quien}"

    def clean(self):
        if not self.cedula and not self.usuario_id:
            raise ValidationError(
                'Un veto debe identificar al sancionado por cédula o por usuario.'
            )
        if self.fecha_fin and self.fecha_inicio and self.fecha_fin < self.fecha_inicio:
            raise ValidationError({
                'fecha_fin': 'La fecha de fin del bloqueo no puede ser anterior a la de inicio.'
            })

    # ── Vigencia ────────────────────────────────────────────────────────
    @property
    def esta_vigente(self):
        """True si este veto todavía bloquea reservas: está ACTIVO y aún no
        se cumple `fecha_fin` (o el bloqueo es indefinido)."""
        if self.estado != self.ACTIVO:
            return False
        return self.fecha_fin is None or date.today() < self.fecha_fin

    @property
    def es_indefinido(self):
        return self.fecha_fin is None

    @property
    def dias_restantes(self):
        """Días de bloqueo que faltan; None si es indefinido, 0 si ya venció."""
        if self.fecha_fin is None:
            return None
        return max((self.fecha_fin - date.today()).days, 0)

    # ── Reglas de remoción ──────────────────────────────────────────────
    def puede_remover(self, usuario):
        """Reglas de quién puede levantar el veto:
        - NO_CANCELO y RETRASO: Laboratorista o Administrador.
        - DANO y FALTA_INSUMO: solo Administrador (tras verificar reposición).
        """
        rol = getattr(getattr(usuario, 'rol', None), 'nombre', None)
        if rol == 'Administrador':
            return True
        if rol == 'Laboratorio':
            return self.tipo in self.TIPOS_REMOVIBLES_POR_LABORATORISTA
        return False

    def resolver(self, usuario, pagado=False):
        """Levanta el veto. `pagado=True` lo marca PAGADO (reposición
        verificada, para DANO/FALTA_INSUMO); si no, RESUELTO."""
        from django.utils import timezone

        self.estado = self.PAGADO if pagado else self.RESUELTO
        self.resuelto_por = usuario
        self.fecha_resolucion = timezone.now()
        self.save(update_fields=['estado', 'resuelto_por', 'fecha_resolucion'])

    # ── Consultas ───────────────────────────────────────────────────────
    @classmethod
    def filtro_persona(cls, cedula=None, usuario=None):
        """Q que casa los vetos de una persona por cédula o por usuario."""
        q = Q()
        if cedula:
            q |= Q(cedula=cedula)
        if usuario is not None:
            q |= Q(usuario=usuario)
        if not q:
            # Ni cédula ni usuario: no casa con nada (evita traer todo).
            return Q(pk__in=[])
        return q

    @classmethod
    def vigentes_para(cls, cedula=None, usuario=None):
        """Vetos que hoy bloquean a la persona indicada."""
        hoy = date.today()
        return cls.objects.filter(
            cls.filtro_persona(cedula=cedula, usuario=usuario),
            estado=cls.ACTIVO,
        ).filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gt=hoy))

    # ── Fábricas de castigo ─────────────────────────────────────────────
    @classmethod
    def _fecha_fin_desde_hoy(cls, dias):
        return date.today() + timedelta(days=dias)

    @classmethod
    def calcular_dias_no_cancelo(cls, cedula=None, usuario=None):
        """1 día normalmente; 7 si con esta ya van ACUMULACION_NO_CANCELO
        infracciones NO_CANCELO del mismo solicitante (contando cualquier
        estado — la reincidencia pesa aunque los vetos previos ya se hayan
        levantado)."""
        previos = cls.objects.filter(
            cls.filtro_persona(cedula=cedula, usuario=usuario),
            tipo=cls.NO_CANCELO,
        ).count()
        if previos + 1 >= cls.ACUMULACION_NO_CANCELO:
            return cls.DIAS_NO_CANCELO_AGRAVADO
        return cls.DIAS_NO_CANCELO
