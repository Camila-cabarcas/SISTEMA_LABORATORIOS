"""
views_personal.py — laboratorio
Sección «Personal»: cuentas de laboratorista, cuenta de monitor de cada
laboratorio, fichas de monitor (personas sin cuenta) y descripción del
laboratorio. Mismo patrón que views_categorias.py.

Toda la lógica y las reglas están en laboratorio/services/personal.py; estas
vistas solo arman formularios, llaman al servicio y muestran sus errores:
- SinPermisoPersonal → página «Sin permiso» con el mensaje, estado 403.
- DatosPersonalInvalidos → el formulario con los errores por campo, o un
  mensaje de error y vuelta a la lista en las acciones sin formulario.

Permisos (users/helpers.py, fijos por rol):
- Administrador: todo, en cualquier laboratorio.
- Laboratorista: ve Personal de su laboratorio, administra sus fichas de
  monitor y su descripción. No administra cuentas.
- Monitor y otros roles: 403. Anónimo: al login.

Las bajas y el borrado piden la contraseña admin (requiere_contrasena_admin).
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from users.decorators import requiere_contrasena_admin
from users.helpers import (
    puede_administrar_personal,
    puede_editar_descripcion,
    puede_gestionar_fichas,
    puede_ver_personal,
)
from users.models import Usuario
from users.roles import LABORATORISTA, MONITOR

from .forms import CuentaPersonalForm, DescripcionLaboratorioForm, FichaMonitorForm
from .models import FichaMonitor, Laboratorio
from .services import personal
from .services.personal import DatosPersonalInvalidos, SinPermisoPersonal

URL_LISTA = 'personal'


# ── Utilidades ──────────────────────────────────────────────────────────────

def _sin_permiso(request, mensaje):
    return render(request, 'users/sin_permiso.html', {'mensaje': mensaje}, status=403)


def _a_formulario(form, error):
    """Copia los errores del servicio al formulario (por campo si el
    formulario lo tiene; si no, como error general)."""
    for campo, mensajes in error.errores.items():
        destino = campo if campo in form.fields else None
        for mensaje in mensajes:
            form.add_error(destino, mensaje)


def _su_laboratorio(usuario):
    """El laboratorio de una cuenta Laboratorista (tiene a lo sumo uno)."""
    return usuario.laboratorios_asignados.first()


def _laboratorio_de_peticion(request):
    """laboratorio_id de POST o de la query (?laboratorio=); si no viene y
    quien pide es laboratorista, el suyo."""
    lab_id = request.POST.get('laboratorio_id') or request.GET.get('laboratorio')
    if lab_id:
        return get_object_or_404(Laboratorio, id=lab_id)
    return _su_laboratorio(request.user)


def _cuenta(id, rol):
    return get_object_or_404(Usuario.objects.select_related('rol'), id=id, rol__nombre=rol)


def _volver(request, laboratorio=None):
    """Vuelve a donde se hizo la acción: el detalle del laboratorio si el
    formulario mandó volver=detalle, o la lista de Personal."""
    if laboratorio is not None and request.POST.get('volver') == 'detalle':
        return redirect(f"{reverse('detalle_laboratorio', args=[laboratorio.id])}?seccion=personal")
    return redirect(URL_LISTA)


# ── Lista ───────────────────────────────────────────────────────────────────

@login_required
def lista_personal(request):
    usuario = request.user
    if puede_administrar_personal(usuario):
        laboratorios = list(Laboratorio.objects.order_by('nombre'))
        avisos = list(personal.cuentas_activas_sin_laboratorio())
        dadas_de_baja = list(
            Usuario.objects.filter(is_active=False, rol__nombre__in=[LABORATORISTA, MONITOR])
            .select_related('rol').order_by('rol__nombre', 'username'))
        for cuenta in dadas_de_baja:
            cuenta.se_puede_eliminar = (cuenta.rol.nombre == LABORATORISTA
                                        and not personal.datos_que_impiden_borrar(cuenta))
    else:
        laboratorio = _su_laboratorio(usuario)
        if laboratorio is None or not puede_ver_personal(usuario, laboratorio):
            return _sin_permiso(request, 'La sección Personal es para el Administrador y los laboratoristas.')
        laboratorios, avisos, dadas_de_baja = [laboratorio], [], []

    return render(request, 'laboratorio/personal/lista.html', {
        'bloques': [personal.personal_del_laboratorio(lab) for lab in laboratorios],
        'es_admin': puede_administrar_personal(usuario),
        'avisos': avisos,
        'dadas_de_baja': dadas_de_baja,
        'todos_los_laboratorios': laboratorios,
    })


# ── Cuentas de laboratorista (solo Administrador) ───────────────────────────

def _solo_admin(request):
    if not puede_administrar_personal(request.user):
        return _sin_permiso(request, 'Solo el Administrador administra cuentas de Personal.')
    return None


@login_required
def crear_laboratorista(request):
    if (denegado := _solo_admin(request)):
        return denegado
    inicial = {}
    if request.GET.get('laboratorio'):
        inicial['laboratorio'] = request.GET['laboratorio']
    form = CuentaPersonalForm(request.POST or None, initial=inicial)
    if request.method == 'POST' and form.is_valid():
        datos = form.cleaned_data
        try:
            cuenta = personal.crear_laboratorista(datos, datos['laboratorio'], request.user)
        except SinPermisoPersonal as e:
            return _sin_permiso(request, str(e))
        except DatosPersonalInvalidos as e:
            _a_formulario(form, e)
        else:
            messages.success(request, f'Cuenta de laboratorista "{cuenta.username}" creada.')
            return redirect(URL_LISTA)
    return render(request, 'laboratorio/personal/laboratorista_form.html', {'form': form, 'cuenta': None})


@login_required
def editar_laboratorista(request, id):
    if (denegado := _solo_admin(request)):
        return denegado
    cuenta = _cuenta(id, LABORATORISTA)
    if not cuenta.is_active:
        messages.error(request, f'La cuenta "{cuenta.username}" está dada de baja: no se puede editar.')
        return redirect(URL_LISTA)
    inicial = {campo: getattr(cuenta, campo) for campo in personal.CAMPOS_CUENTA}
    inicial['laboratorio'] = _su_laboratorio(cuenta)
    form = CuentaPersonalForm(request.POST or None, initial=inicial, editando=True)
    if request.method == 'POST' and form.is_valid():
        datos = form.cleaned_data
        try:
            with transaction.atomic():
                personal.editar_laboratorista(cuenta, datos, request.user)
                if datos['laboratorio'] != inicial['laboratorio']:
                    personal.cambiar_laboratorio(cuenta, datos['laboratorio'], request.user)
        except SinPermisoPersonal as e:
            return _sin_permiso(request, str(e))
        except DatosPersonalInvalidos as e:
            cuenta.refresh_from_db()
            _a_formulario(form, e)
        else:
            messages.success(request, f'Cuenta "{cuenta.username}" actualizada.')
            return redirect(URL_LISTA)
    return render(request, 'laboratorio/personal/laboratorista_form.html', {'form': form, 'cuenta': cuenta})


def _contexto_cuenta(rol):
    return lambda r, *a, **kw: f"{rol} - {Usuario.objects.get(id=kw['id']).username}"


@login_required
def baja_laboratorista(request, id):
    """GET: página de confirmación (qué pasa y si se puede eliminar).
    POST: pide la contraseña admin y da de baja."""
    if (denegado := _solo_admin(request)):
        return denegado
    cuenta = _cuenta(id, LABORATORISTA)
    if request.method != 'POST':
        return render(request, 'laboratorio/personal/confirmar_baja.html', {
            'cuenta': cuenta,
            'tipo': 'laboratorista',
            'laboratorio': _su_laboratorio(cuenta),
            'datos_asociados': personal.datos_que_impiden_borrar(cuenta),
            'url_baja': reverse('baja_laboratorista', args=[cuenta.id]),
            'url_eliminar': reverse('eliminar_laboratorista', args=[cuenta.id]),
        })
    return _baja_laboratorista_confirmada(request, id=id)


@requiere_contrasena_admin(titulo_accion='Dar de baja la cuenta de laboratorista',
                           get_contexto=_contexto_cuenta('Laboratorista'))
def _baja_laboratorista_confirmada(request, id):
    cuenta = _cuenta(id, LABORATORISTA)
    try:
        personal.dar_de_baja_laboratorista(cuenta, request.user)
    except SinPermisoPersonal as e:
        return _sin_permiso(request, str(e))
    except DatosPersonalInvalidos as e:
        messages.error(request, str(e))
    else:
        messages.success(request, f'Cuenta "{cuenta.username}" dada de baja: inactiva y sin laboratorio.')
    return redirect(URL_LISTA)


@login_required
@require_POST
def eliminar_laboratorista(request, id):
    """Borrado real, solo si la cuenta no tiene datos asociados. Si los
    tiene, se avisa sin pedir la contraseña."""
    if (denegado := _solo_admin(request)):
        return denegado
    cuenta = _cuenta(id, LABORATORISTA)
    asociados = personal.datos_que_impiden_borrar(cuenta)
    if asociados:
        detalle = ', '.join(f'{cantidad} {descripcion}' for descripcion, cantidad in asociados)
        messages.error(request, f'No se puede eliminar la cuenta "{cuenta.username}" porque tiene datos '
                                f'asociados ({detalle}). Dala de baja en su lugar.')
        return redirect(URL_LISTA)
    return _eliminar_laboratorista_confirmado(request, id=id)


@requiere_contrasena_admin(titulo_accion='Eliminar definitivamente la cuenta de laboratorista',
                           get_contexto=_contexto_cuenta('Laboratorista'))
def _eliminar_laboratorista_confirmado(request, id):
    cuenta = _cuenta(id, LABORATORISTA)
    username = cuenta.username
    try:
        personal.eliminar_laboratorista(cuenta, request.user)
    except SinPermisoPersonal as e:
        return _sin_permiso(request, str(e))
    except DatosPersonalInvalidos as e:
        messages.error(request, str(e))
    else:
        messages.success(request, f'Cuenta "{username}" eliminada.')
    return redirect(URL_LISTA)


# ── Cuenta de monitor (solo Administrador) ──────────────────────────────────

@login_required
def crear_monitor(request):
    if (denegado := _solo_admin(request)):
        return denegado
    inicial = {}
    if request.GET.get('laboratorio'):
        inicial['laboratorio'] = request.GET['laboratorio']
    form = CuentaPersonalForm(request.POST or None, initial=inicial)
    if request.method == 'POST' and form.is_valid():
        datos = form.cleaned_data
        try:
            cuenta = personal.crear_monitor_laboratorio(datos, datos['laboratorio'], request.user)
        except SinPermisoPersonal as e:
            return _sin_permiso(request, str(e))
        except DatosPersonalInvalidos as e:
            _a_formulario(form, e)
        else:
            messages.success(request, f'Cuenta de monitor "{cuenta.username}" creada.')
            return redirect(URL_LISTA)
    return render(request, 'laboratorio/personal/monitor_form.html', {'form': form, 'cuenta': None})


@login_required
def editar_monitor(request, id):
    """El laboratorio de la cuenta de monitor no se cambia aquí: para pasarla
    a otro laboratorio se da de baja y se crea una nueva."""
    if (denegado := _solo_admin(request)):
        return denegado
    cuenta = _cuenta(id, MONITOR)
    if not cuenta.is_active:
        messages.error(request, f'La cuenta "{cuenta.username}" está dada de baja: no se puede editar.')
        return redirect(URL_LISTA)
    inicial = {campo: getattr(cuenta, campo) for campo in personal.CAMPOS_CUENTA}
    form = CuentaPersonalForm(request.POST or None, initial=inicial, editando=True, con_laboratorio=False)
    if request.method == 'POST' and form.is_valid():
        try:
            personal.editar_monitor(cuenta, form.cleaned_data, request.user)
        except SinPermisoPersonal as e:
            return _sin_permiso(request, str(e))
        except DatosPersonalInvalidos as e:
            cuenta.refresh_from_db()
            _a_formulario(form, e)
        else:
            messages.success(request, f'Cuenta de monitor "{cuenta.username}" actualizada.')
            return redirect(URL_LISTA)
    return render(request, 'laboratorio/personal/monitor_form.html', {
        'form': form, 'cuenta': cuenta, 'laboratorio': cuenta.laboratorios_monitoreados.first(),
    })


@login_required
def baja_monitor(request, id):
    if (denegado := _solo_admin(request)):
        return denegado
    cuenta = _cuenta(id, MONITOR)
    if request.method != 'POST':
        return render(request, 'laboratorio/personal/confirmar_baja.html', {
            'cuenta': cuenta,
            'tipo': 'monitor',
            'laboratorio': cuenta.laboratorios_monitoreados.first(),
            'url_baja': reverse('baja_monitor', args=[cuenta.id]),
        })
    return _baja_monitor_confirmada(request, id=id)


@requiere_contrasena_admin(titulo_accion='Dar de baja la cuenta de monitor',
                           get_contexto=_contexto_cuenta('Monitor'))
def _baja_monitor_confirmada(request, id):
    cuenta = _cuenta(id, MONITOR)
    try:
        personal.dar_de_baja_monitor(cuenta, request.user)
    except SinPermisoPersonal as e:
        return _sin_permiso(request, str(e))
    except DatosPersonalInvalidos as e:
        messages.error(request, str(e))
    else:
        messages.success(request, f'Cuenta de monitor "{cuenta.username}" dada de baja.')
    return redirect(URL_LISTA)


# ── Fichas de monitor (Administrador; laboratorista en su laboratorio) ──────

@login_required
def crear_ficha(request):
    laboratorio = _laboratorio_de_peticion(request)
    if laboratorio is None or not puede_gestionar_fichas(request.user, laboratorio):
        return _sin_permiso(request, 'No puedes administrar las fichas de monitor de este laboratorio.')
    form = FichaMonitorForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            ficha = personal.agregar_ficha(form.cleaned_data, laboratorio, request.user)
        except SinPermisoPersonal as e:
            return _sin_permiso(request, str(e))
        except DatosPersonalInvalidos as e:
            _a_formulario(form, e)
        else:
            messages.success(request, f'Ficha de "{ficha}" agregada a {laboratorio.nombre}.')
            return _volver(request, laboratorio)
    return render(request, 'laboratorio/personal/ficha_form.html', {
        'form': form, 'ficha': None, 'laboratorio': laboratorio,
    })


@login_required
def editar_ficha(request, id):
    ficha = get_object_or_404(FichaMonitor, id=id)
    puede = puede_administrar_personal(request.user) or any(
        puede_gestionar_fichas(request.user, lab) for lab in ficha.laboratorios.all())
    if not puede:
        return _sin_permiso(request, 'No puedes editar esta ficha: no está en un laboratorio a tu cargo.')
    inicial = {campo: getattr(ficha, campo) for campo in (*personal.CAMPOS_FICHA, 'activo')}
    form = FichaMonitorForm(request.POST or None, initial=inicial)
    if request.method == 'POST' and form.is_valid():
        try:
            personal.editar_ficha(ficha, form.cleaned_data, request.user)
        except SinPermisoPersonal as e:
            return _sin_permiso(request, str(e))
        except DatosPersonalInvalidos as e:
            ficha.refresh_from_db()
            _a_formulario(form, e)
        else:
            messages.success(request, f'Ficha de "{ficha}" actualizada.')
            return redirect(URL_LISTA)
    return render(request, 'laboratorio/personal/ficha_form.html', {
        'form': form, 'ficha': ficha, 'laboratorio': None,
        'otros_laboratorios': ficha.laboratorios.order_by('nombre'),
    })


@login_required
@require_POST
def quitar_ficha(request, id):
    ficha = get_object_or_404(FichaMonitor, id=id)
    laboratorio = _laboratorio_de_peticion(request)
    if laboratorio is None:
        messages.error(request, 'Indica de qué laboratorio quitar la ficha.')
        return redirect(URL_LISTA)
    nombre = str(ficha)
    try:
        borrada = personal.quitar_ficha_de_laboratorio(ficha, laboratorio, request.user)
    except SinPermisoPersonal as e:
        return _sin_permiso(request, str(e))
    except DatosPersonalInvalidos as e:
        messages.error(request, str(e))
        return _volver(request, laboratorio)
    if borrada:
        messages.success(request, f'Ficha de "{nombre}" quitada de {laboratorio.nombre} y borrada '
                                  f'(no estaba en ningún otro laboratorio).')
    else:
        messages.success(request, f'Ficha de "{nombre}" quitada de {laboratorio.nombre}.')
    return _volver(request, laboratorio)


@login_required
@require_POST
def vincular_ficha(request, id):
    ficha = get_object_or_404(FichaMonitor, id=id)
    laboratorio = _laboratorio_de_peticion(request)
    if laboratorio is None:
        messages.error(request, 'Elige el laboratorio al que vincular la ficha.')
        return redirect(URL_LISTA)
    try:
        personal.vincular_ficha_a_laboratorio(ficha, laboratorio, request.user)
    except SinPermisoPersonal as e:
        return _sin_permiso(request, str(e))
    except DatosPersonalInvalidos as e:
        messages.error(request, str(e))
    else:
        messages.success(request, f'Ficha de "{ficha}" vinculada a {laboratorio.nombre}.')
    return redirect(URL_LISTA)


# ── Descripción del laboratorio ─────────────────────────────────────────────

@login_required
def editar_descripcion(request, lab_id):
    laboratorio = get_object_or_404(Laboratorio, id=lab_id)
    if not puede_editar_descripcion(request.user, laboratorio):
        return _sin_permiso(request, 'No puedes editar la descripción de este laboratorio.')
    form = DescripcionLaboratorioForm(request.POST or None, initial={'descripcion': laboratorio.descripcion})
    if request.method == 'POST' and form.is_valid():
        try:
            personal.actualizar_descripcion_laboratorio(
                laboratorio, form.cleaned_data['descripcion'], request.user)
        except SinPermisoPersonal as e:
            return _sin_permiso(request, str(e))
        messages.success(request, 'Descripción actualizada.')
        return redirect(f"{reverse('detalle_laboratorio', args=[laboratorio.id])}?seccion=descripcion")
    return render(request, 'laboratorio/personal/descripcion_form.html', {
        'form': form, 'laboratorio': laboratorio,
    })
