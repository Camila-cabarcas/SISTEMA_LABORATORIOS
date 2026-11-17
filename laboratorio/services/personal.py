"""
personal.py — laboratorio
Sección «Personal»: cuentas de laboratorista, cuenta compartida de monitor
por laboratorio, fichas de monitor (personas sin cuenta) y descripción del
laboratorio.

Reglas (decididas por Camila, fase Personal):
- Laboratorista: cuenta Usuario con correo @udea.edu.co, usuario, nombre,
  apellido y EXACTAMENTE un laboratorio mientras esté activa. La base
  garantiza "a lo sumo uno" (AsignacionLaboratorista); este servicio, "al
  menos uno". Un laboratorio puede tener varios laboratoristas.
- Monitor: una cuenta por laboratorio y un laboratorio por cuenta (lo
  garantiza también la base, AsignacionMonitor).
- Dar de baja = desactivar la cuenta y quitarle el laboratorio. No se borra.
  El borrado real solo se permite si la cuenta no tiene datos asociados.
- Solo el Administrador administra cuentas. Fichas y descripción: el
  Administrador en cualquier laboratorio, el laboratorista en el suyo.

Cada función verifica permisos al inicio. Errores:
- SinPermisoPersonal (también es PermissionDenied: si nadie la captura,
  Django responde 403, no 500).
- DatosPersonalInvalidos: `errores` es {campo: [mensajes]} para mostrarlos
  en el formulario; str() da un resumen para un mensaje flash.
Las vistas (etapa 3) las capturan y muestran el mensaje.
"""
from types import SimpleNamespace

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models.deletion import Collector, ProtectedError, RestrictedError

from laboratorio.models import AsignacionLaboratorista, AsignacionMonitor, FichaMonitor
from users.helpers import (
    puede_administrar_personal,
    puede_editar_descripcion,
    puede_gestionar_fichas,
)
from users.models import Rol, Usuario
from users.roles import LABORATORISTA, MONITOR
from users.validators import validar_correo_institucional


# ── Errores ─────────────────────────────────────────────────────────────────

class PersonalError(Exception):
    """Base de los errores de este servicio. El mensaje va al usuario."""


class SinPermisoPersonal(PersonalError, PermissionDenied):
    pass


class DatosPersonalInvalidos(PersonalError):

    def __init__(self, errores):
        if isinstance(errores, str):
            errores = {'__all__': [errores]}
        self.errores = {campo: list(mensajes) for campo, mensajes in errores.items()}
        super().__init__(' '.join(m for mensajes in self.errores.values() for m in mensajes))


def _exigir(condicion, mensaje):
    if not condicion:
        raise SinPermisoPersonal(mensaje)


def _exigir_admin(usuario):
    _exigir(puede_administrar_personal(usuario), 'Solo el Administrador puede administrar cuentas de Personal.')


# ── Cuentas (laboratorista y monitor) ───────────────────────────────────────

CAMPOS_CUENTA = ('username', 'email', 'first_name', 'last_name')


def _limpio(datos, campo):
    return (datos.get(campo) or '').strip()


def _validar_y_aplicar_cuenta(usuario, datos, *, exigir_password):
    """Copia `datos` a `usuario` (sin guardar) y valida todo junto. Lanza
    DatosPersonalInvalidos con los errores por campo."""
    errores = {}

    def error(campo, mensaje):
        errores.setdefault(campo, []).append(mensaje)

    valores = {campo: _limpio(datos, campo) for campo in CAMPOS_CUENTA}
    for campo, etiqueta in (('username', 'El nombre de usuario'), ('email', 'El correo'),
                            ('first_name', 'El nombre'), ('last_name', 'El apellido')):
        if not valores[campo]:
            error(campo, f'{etiqueta} es obligatorio.')

    if valores['email']:
        try:
            validar_correo_institucional(valores['email'])
        except ValidationError as e:
            for mensaje in e.messages:
                error('email', mensaje)

    # El login acepta el usuario sin distinguir mayúsculas: dos cuentas
    # "Ana" y "ana" lo volverían ambiguo.
    if valores['username'] and Usuario.objects.filter(
            username__iexact=valores['username']).exclude(pk=usuario.pk).exists():
        error('username', 'Ya existe una cuenta con ese nombre de usuario.')

    for campo, valor in valores.items():
        setattr(usuario, campo, valor)

    password = datos.get('password') or ''
    if exigir_password and not password:
        error('password', 'La contraseña inicial es obligatoria.')
    if password:
        try:
            validate_password(password, usuario)
        except ValidationError as e:
            for mensaje in e.messages:
                error('password', mensaje)
        usuario.set_password(password)

    try:
        # Validadores del modelo, unicidad de username y correo (sin
        # distinguir mayúsculas, restricción usuario_email_unico_ci).
        usuario.full_clean(exclude=['password'])  # ya validada arriba
    except ValidationError as e:
        for campo, mensajes in e.message_dict.items():
            for mensaje in mensajes:
                if mensaje not in errores.get(campo, []):
                    error(campo, mensaje)

    if errores:
        raise DatosPersonalInvalidos(errores)


def _cuenta_con_rol(usuario, rol):
    if not usuario.rol or usuario.rol.nombre != rol:
        raise DatosPersonalInvalidos(f'La cuenta "{usuario.username}" no es de rol {rol}.')


def _exigir_laboratorio(laboratorio):
    if laboratorio is None:
        raise DatosPersonalInvalidos({'laboratorio': ['Selecciona un laboratorio.']})


def _crear_cuenta(datos, rol_nombre):
    usuario = Usuario(rol=Rol.objects.get(nombre=rol_nombre), is_active=True)
    _validar_y_aplicar_cuenta(usuario, datos, exigir_password=True)
    usuario.save()
    return usuario


def _dar_de_baja(usuario, modelo_asignacion):
    with transaction.atomic():
        modelo_asignacion.objects.filter(usuario=usuario).delete()
        if usuario.is_active:
            usuario.is_active = False
            usuario.save(update_fields=['is_active'])
    return usuario


# Laboratorista

def crear_laboratorista(datos, laboratorio, admin):
    """Crea una cuenta Laboratorista activa con su único laboratorio. `datos`:
    username, email (UdeA), first_name, last_name, password. Todo o nada."""
    _exigir_admin(admin)
    _exigir_laboratorio(laboratorio)
    with transaction.atomic():
        usuario = _crear_cuenta(datos, LABORATORISTA)
        AsignacionLaboratorista.objects.create(usuario=usuario, laboratorio=laboratorio)
    return usuario


def editar_laboratorista(usuario, datos, admin):
    """Cambia usuario, correo, nombre y apellido; la contraseña solo si
    `datos['password']` viene con valor. El laboratorio se cambia con
    cambiar_laboratorio()."""
    _exigir_admin(admin)
    _cuenta_con_rol(usuario, LABORATORISTA)
    _validar_y_aplicar_cuenta(usuario, datos, exigir_password=False)
    usuario.save()
    return usuario


def cambiar_laboratorio(usuario, laboratorio_nuevo, admin):
    """Reemplaza el laboratorio de la cuenta: sigue teniendo exactamente uno."""
    _exigir_admin(admin)
    _cuenta_con_rol(usuario, LABORATORISTA)
    _exigir_laboratorio(laboratorio_nuevo)
    with transaction.atomic():
        AsignacionLaboratorista.objects.filter(usuario=usuario).delete()
        AsignacionLaboratorista.objects.create(usuario=usuario, laboratorio=laboratorio_nuevo)
    return usuario


def dar_de_baja_laboratorista(usuario, admin):
    """Desactiva la cuenta y le quita el laboratorio. No borra nada más:
    préstamos, reservas y movimientos siguen asociados a la cuenta."""
    _exigir_admin(admin)
    _cuenta_con_rol(usuario, LABORATORISTA)
    return _dar_de_baja(usuario, AsignacionLaboratorista)


# Qué datos impiden el borrado real, con el nombre que ve el usuario. Los
# primeros cuatro son los que pidió Camila; el resto se borraría en cascada
# junto con la cuenta (ver datos_que_impiden_borrar).
DATOS_ASOCIADOS = (
    ('prestamos', 'Prestamo', 'responsable', 'préstamos'),
    ('reservas', 'Reserva', 'usuario', 'reservas'),
    ('inventario', 'MovimientoInventario', 'usuario', 'movimientos de inventario'),
    ('prestamos', 'InspeccionItem', 'inspector', 'inspecciones'),
)
# Al borrar una cuenta se pueden ir con ella sus asignaciones (es justo lo
# que se quiere) y nada más.
_BORRABLES_CON_LA_CUENTA = {AsignacionLaboratorista, AsignacionMonitor}


def datos_que_impiden_borrar(usuario):
    """[(descripción, cantidad)] de lo que impide borrar la cuenta: los
    datos de DATOS_ASOCIADOS y cualquier otro registro que se borraría en
    cascada (p. ej. ítems de inventario con updated_by, solicitudes de
    reserva, cursos, historial del admin). Vacío = se puede borrar."""
    from django.apps import apps

    encontrados = []
    for app, modelo, campo, descripcion in DATOS_ASOCIADOS:
        cantidad = apps.get_model(app, modelo).objects.filter(**{campo: usuario}).count()
        if cantidad:
            encontrados.append((descripcion, cantidad))

    ya_contados = {apps.get_model(app, modelo) for app, modelo, _, _ in DATOS_ASOCIADOS}

    def se_ignora(modelo):
        # La cuenta misma, sus asignaciones, lo ya contado arriba y las
        # tablas automáticas de Django (grupos y permisos de la cuenta).
        return (modelo is Usuario or modelo in _BORRABLES_CON_LA_CUENTA
                or modelo in ya_contados or modelo._meta.auto_created)

    collector = Collector(using='default')
    try:
        collector.collect([usuario])
    except (ProtectedError, RestrictedError) as e:
        encontrados.append(('registros protegidos', len(getattr(e, 'protected_objects', None)
                                                       or getattr(e, 'restricted_objects', ()))))
        return encontrados
    for modelo, objetos in collector.data.items():
        if not se_ignora(modelo) and objetos:
            encontrados.append((str(modelo._meta.verbose_name_plural), len(objetos)))
    for qs in collector.fast_deletes:
        if not se_ignora(qs.model):
            cantidad = qs.count()
            if cantidad:
                encontrados.append((str(qs.model._meta.verbose_name_plural), cantidad))
    return encontrados


def eliminar_laboratorista(usuario, admin):
    """Borra la cuenta SOLO si no tiene datos asociados. Si los tiene,
    lanza DatosPersonalInvalidos y no borra nada: en ese caso hay que darla
    de baja (dar_de_baja_laboratorista)."""
    _exigir_admin(admin)
    _cuenta_con_rol(usuario, LABORATORISTA)
    asociados = datos_que_impiden_borrar(usuario)
    if asociados:
        detalle = ', '.join(f'{cantidad} {descripcion}' for descripcion, cantidad in asociados)
        raise DatosPersonalInvalidos(
            f'No se puede eliminar la cuenta "{usuario.username}" porque tiene datos asociados '
            f'({detalle}). Dala de baja en su lugar.'
        )
    usuario.delete()


# Monitor (cuenta compartida del laboratorio)

def crear_monitor_laboratorio(datos, laboratorio, admin):
    """Crea la cuenta Monitor de `laboratorio`. Rechaza si ya tiene una."""
    _exigir_admin(admin)
    _exigir_laboratorio(laboratorio)
    if AsignacionMonitor.objects.filter(laboratorio=laboratorio).exists():
        raise DatosPersonalInvalidos({'laboratorio': ['Este laboratorio ya tiene una cuenta de monitor.']})
    try:
        with transaction.atomic():
            usuario = _crear_cuenta(datos, MONITOR)
            AsignacionMonitor.objects.create(usuario=usuario, laboratorio=laboratorio)
    except IntegrityError:
        # Otra petición creó la cuenta de monitor de este laboratorio entre
        # la verificación y el alta (laboratorio_una_cuenta_monitor).
        raise DatosPersonalInvalidos({'laboratorio': ['Este laboratorio ya tiene una cuenta de monitor.']})
    return usuario


def editar_monitor(usuario, datos, admin):
    _exigir_admin(admin)
    _cuenta_con_rol(usuario, MONITOR)
    _validar_y_aplicar_cuenta(usuario, datos, exigir_password=False)
    usuario.save()
    return usuario


def dar_de_baja_monitor(usuario, admin):
    """Desactiva la cuenta de monitor y la quita del laboratorio, que queda
    libre para una cuenta nueva."""
    _exigir_admin(admin)
    _cuenta_con_rol(usuario, MONITOR)
    return _dar_de_baja(usuario, AsignacionMonitor)


# Consultas de solo lectura

def personal_del_laboratorio(laboratorio):
    """Lo que muestra la sección Personal de un laboratorio:
    - laboratoristas: cuentas Laboratorista activas (puede haber varias),
    - monitor: la cuenta Monitor del laboratorio, o None si no tiene,
    - fichas: fichas de monitor del laboratorio,
    - total: cuántas personas/cuentas hay en total (contador del sidebar)."""
    laboratoristas = list(laboratorio.laboratoristas.filter(is_active=True).order_by('username'))
    monitor = laboratorio.monitores.order_by('username').first()
    fichas = list(laboratorio.fichas_monitor.prefetch_related('laboratorios').order_by('apellido', 'nombre'))
    return SimpleNamespace(
        laboratorio=laboratorio,
        laboratoristas=laboratoristas,
        monitor=monitor,
        fichas=fichas,
        total=len(laboratoristas) + len(fichas) + (1 if monitor else 0),
    )


def cuentas_activas_sin_laboratorio():
    """Cuentas Laboratorista o Monitor activas que no tienen laboratorio
    (incumplen "exactamente uno"). Solo lectura: no corrige nada."""
    return (Usuario.objects
            .filter(is_active=True, rol__nombre__in=[LABORATORISTA, MONITOR])
            .filter(laboratorios_asignados__isnull=True, laboratorios_monitoreados__isnull=True)
            .select_related('rol').order_by('rol__nombre', 'username'))


# ── Fichas de monitor ───────────────────────────────────────────────────────

CAMPOS_FICHA = ('nombre', 'apellido', 'correo', 'telefono', 'descripcion')


def _validar_y_aplicar_ficha(ficha, datos):
    errores = {}
    for campo in CAMPOS_FICHA:
        if campo in datos:
            setattr(ficha, campo, (datos.get(campo) or '').strip())
    if 'activo' in datos:
        ficha.activo = bool(datos['activo'])
    if ficha.correo:
        try:
            validate_email(ficha.correo)  # formato; sin restricción de dominio
        except ValidationError:
            errores.setdefault('correo', []).append('Escribe un correo válido.')
    try:
        ficha.full_clean(exclude=['creado_por'])
    except ValidationError as e:
        for campo, mensajes in e.message_dict.items():
            for mensaje in mensajes:
                if mensaje not in errores.get(campo, []):
                    errores.setdefault(campo, []).append(mensaje)
    if errores:
        raise DatosPersonalInvalidos(errores)


def _exigir_fichas(usuario, laboratorio):
    _exigir(puede_gestionar_fichas(usuario, laboratorio),
            'No puedes administrar las fichas de monitor de este laboratorio.')


def agregar_ficha(datos, laboratorio, usuario):
    """Crea una ficha nueva vinculada a `laboratorio`."""
    _exigir_laboratorio(laboratorio)
    _exigir_fichas(usuario, laboratorio)
    ficha = FichaMonitor(creado_por=usuario)
    _validar_y_aplicar_ficha(ficha, datos)
    with transaction.atomic():
        ficha.save()
        ficha.laboratorios.add(laboratorio)
    return ficha


def editar_ficha(ficha, datos, usuario):
    """El cambio se ve en todos los laboratorios de la ficha. Puede editarla
    quien administre las fichas de alguno de sus laboratorios (el
    laboratorista tiene uno solo: el suyo)."""
    _exigir(puede_administrar_personal(usuario)
            or any(puede_gestionar_fichas(usuario, lab) for lab in ficha.laboratorios.all()),
            'No puedes editar esta ficha: no está en un laboratorio a tu cargo.')
    _validar_y_aplicar_ficha(ficha, datos)
    ficha.save()
    return ficha


def vincular_ficha_a_laboratorio(ficha, laboratorio, usuario):
    """Agrega una ficha existente a otro laboratorio (en vez de duplicarla).
    El Administrador, o el laboratorista del laboratorio destino."""
    _exigir_laboratorio(laboratorio)
    _exigir_fichas(usuario, laboratorio)
    ficha.laboratorios.add(laboratorio)
    return ficha


def quitar_ficha_de_laboratorio(ficha, laboratorio, usuario):
    """Desvincula la ficha de `laboratorio`. Si no le queda ninguno, la
    borra. Devuelve True si la ficha se borró."""
    _exigir_fichas(usuario, laboratorio)
    with transaction.atomic():
        if not ficha.laboratorios.filter(pk=laboratorio.pk).exists():
            raise DatosPersonalInvalidos('La ficha no está en este laboratorio.')
        ficha.laboratorios.remove(laboratorio)
        if not ficha.laboratorios.exists():
            ficha.delete()
            return True
    return False


# ── Descripción del laboratorio ─────────────────────────────────────────────

def actualizar_descripcion_laboratorio(laboratorio, texto, usuario):
    """Texto plano: se guarda tal cual (sin espacios al inicio y al final).
    Las plantillas lo escapan al mostrarlo."""
    _exigir(puede_editar_descripcion(usuario, laboratorio),
            'No puedes editar la descripción de este laboratorio.')
    laboratorio.descripcion = (texto or '').strip()
    laboratorio.save(update_fields=['descripcion'])
    return laboratorio
