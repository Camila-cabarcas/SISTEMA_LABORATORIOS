"""
Fase 2, etapa 1 — SOLO DATOS: las cuentas de rol Docente pasan a ser
registros Profesor (sin cuenta) y sus cursos se copian a
Curso.profesor_registro. No borra ninguna cuenta (eso lo hace — sin borrar —
users.0008, que las deja inactivas y sin rol).

Adelante, todo o nada:
a. Descarta la cuenta de prueba e2e_profesor: borra SUS cursos y NO la
   convierte en Profesor. Antes verifica que la cuenta no tenga reservas,
   solicitudes de reserva ni préstamos, y que ninguna solicitud use esos
   cursos; si encuentra algo, falla sin cambiar nada.
b. Cada cuenta Docente restante → Profesor(cedula=codigo, nombre, apellido,
   correo, programa, cuenta_anterior=cuenta). El correo se copia tal cual
   (la validación @udea.edu.co es solo para formularios nuevos).
c. Copia Curso.profesor → Curso.profesor_registro.
d. Verifica que TODOS los cursos tengan profesor_registro; si no, falla con
   la lista de cursos y no cambia nada (la migración es atómica).

Reversa: deja profesor_registro vacío y borra los Profesor con
cuenta_anterior (los creados aquí). Los cursos descartados de e2e_profesor
NO se restauran.
"""
from django.db import migrations

CUENTA_DESCARTADA = 'e2e_profesor'
ROL_DOCENTE = 'Docente'


class DatosInvalidos(Exception):
    pass


def docentes_a_profesores(apps, schema_editor):
    Usuario = apps.get_model('users', 'Usuario')
    Curso = apps.get_model('solicitudes', 'Curso')
    Profesor = apps.get_model('solicitudes', 'Profesor')
    SolicitudReserva = apps.get_model('solicitudes', 'SolicitudReserva')
    SolicitudRegistroCurso = apps.get_model('solicitudes', 'SolicitudRegistroCurso')
    Reserva = apps.get_model('reservas', 'Reserva')
    Prestamo = apps.get_model('prestamos', 'Prestamo')

    # a. Descartar e2e_profesor y sus cursos.
    descartada = Usuario.objects.filter(username=CUENTA_DESCARTADA).first()
    if descartada is not None:
        cursos = Curso.objects.filter(profesor=descartada)
        asociados = {
            'reservas': Reserva.objects.filter(usuario=descartada).count(),
            'solicitudes de reserva': SolicitudReserva.objects.filter(usuario=descartada).count(),
            'préstamos': Prestamo.objects.filter(responsable=descartada).count(),
            'solicitudes de reserva con sus cursos': SolicitudReserva.objects.filter(curso__in=cursos).count(),
            'registros de curso con sus cursos': SolicitudRegistroCurso.objects.filter(curso_creado__in=cursos).count(),
        }
        con_datos = {k: v for k, v in asociados.items() if v}
        if con_datos:
            detalle = ', '.join(f'{v} {k}' for k, v in con_datos.items())
            raise DatosInvalidos(
                f'solicitudes.0012: la cuenta "{CUENTA_DESCARTADA}" tiene datos asociados ({detalle}); '
                f'no se descarta. Revisa esos datos y vuelve a migrar; no se cambió nada.'
            )
        cursos.delete()

    # b. Cuenta Docente → Profesor.
    docentes = Usuario.objects.filter(rol__nombre=ROL_DOCENTE).exclude(username=CUENTA_DESCARTADA).order_by('id')
    sin_cedula = [u.username for u in docentes if not (u.codigo or '').strip()]
    if sin_cedula:
        raise DatosInvalidos(
            'solicitudes.0012: estas cuentas Docente no tienen cédula (Usuario.codigo) y no se pueden '
            f'convertir en Profesor: {", ".join(sin_cedula)}. No se cambió nada.'
        )
    profesor_de_cuenta = {}
    for cuenta in docentes:
        profesor_de_cuenta[cuenta.id] = Profesor.objects.create(
            cedula=cuenta.codigo.strip(),
            nombre=cuenta.first_name or cuenta.username,
            apellido=cuenta.last_name,
            correo=cuenta.email or '',
            programa=cuenta.programa or '',
            activo=True,
            cuenta_anterior=cuenta,
        )

    # c. Copiar el profesor de cada curso.
    for curso in Curso.objects.all():
        profesor = profesor_de_cuenta.get(curso.profesor_id)
        if profesor is not None:
            curso.profesor_registro = profesor
            curso.save(update_fields=['profesor_registro'])

    # d. Ningún curso puede quedar sin profesor_registro.
    huerfanos = list(Curso.objects.filter(profesor_registro__isnull=True)
                     .order_by('codigo').values_list('codigo', 'profesor__username'))
    if huerfanos:
        detalle = ', '.join(f'{codigo} (profesor: {usuario})' for codigo, usuario in huerfanos)
        raise DatosInvalidos(
            'solicitudes.0012: estos cursos no tienen un profesor Docente que se pueda convertir: '
            f'{detalle}. Corrígelos y vuelve a migrar; no se cambió nada.'
        )


def deshacer(apps, schema_editor):
    Curso = apps.get_model('solicitudes', 'Curso')
    Profesor = apps.get_model('solicitudes', 'Profesor')
    Curso.objects.update(profesor_registro=None)  # primero: profesor_registro es PROTECT
    Profesor.objects.filter(cuenta_anterior__isnull=False).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('solicitudes', '0011_ajustes_registro_profesor'),
        # Para la verificación de datos asociados a e2e_profesor.
        ('reservas', '0007_alter_estadoreserva_nombre'),
        ('prestamos', '0009_alter_estadoprestamo_nombre'),
    ]

    operations = [
        migrations.RunPython(docentes_a_profesores, deshacer),
    ]
