"""
asignar_cursos_labs.py — solicitudes
Crea cursos realistas por laboratorio y los asocia a su Laboratorio.

Uso:
    python manage.py asignar_cursos_labs

Idempotente: cada curso se identifica por su código (MECAN-101, ...). Si ya
existe, no se tocan nombre/profesor/estudiantes; solo se corrige el
laboratorio si no coincide. Los laboratorios NO se crean: si ninguno de los
nombres candidatos existe, ese grupo de cursos se omite con un aviso.
"""
import random
import unicodedata

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from laboratorio.models import Laboratorio
from solicitudes.models import Curso, Profesor


# (nombres candidatos del laboratorio, en orden de preferencia) -> cursos
CURSOS_POR_LAB = [
    (['LAB-Mecanica', 'Lab Mecanica'], ['Mecánica I', 'Mecánica II', 'Termodinámica']),
    (['Lab Ondas', 'Laboratorio de ondas'], ['Ondas y Óptica', 'Electromagnetismo']),
    (['Lab Sistemas', 'Lab de Ingenieria de sistemas'], ['Sistemas Digitales', 'Microprocesadores']),
    (['Lab de Ingenieria de sistemas'], ['Telecomunicaciones', 'Redes']),
]


def _normalizar(texto):
    sin_tildes = unicodedata.normalize('NFKD', texto).encode('ascii', 'ignore').decode()
    return ' '.join(sin_tildes.lower().split())


def generar_codigos(nombres):
    """'Mecánica I', 'Mecánica II' -> MECAN-101, MECAN-102. Determinista
    (depende solo del orden de la lista) para que el comando sea idempotente."""
    usados = {}
    codigos = {}
    for nombre in nombres:
        prefijo = _normalizar(nombre).split()[0][:5].upper()
        usados[prefijo] = usados.get(prefijo, 0) + 1
        codigos[nombre] = f"{prefijo}-{100 + usados[prefijo]}"
    return codigos


class Command(BaseCommand):
    help = 'Crea cursos realistas por laboratorio y los asigna (idempotente).'

    def _buscar_laboratorio(self, candidatos, laboratorios):
        por_nombre = {_normalizar(lab.nombre): lab for lab in laboratorios}
        for candidato in candidatos:
            lab = por_nombre.get(_normalizar(candidato))
            if lab:
                return lab
        return None

    @transaction.atomic
    def handle(self, *args, **options):
        # Curso.clean() exige un profesor activo: se reparten los Profesor activos
        # (fase 2: los profesores ya no tienen cuenta).
        profesores = list(Profesor.objects.filter(activo=True).order_by('id'))
        if not profesores:
            raise CommandError('No hay profesores activos; registre al menos uno antes de ejecutar el comando.')

        laboratorios = list(Laboratorio.objects.all())
        codigos = generar_codigos([c for _, cursos in CURSOS_POR_LAB for c in cursos])
        creados = actualizados = sin_cambios = 0
        indice_profesor = 0

        for candidatos, cursos in CURSOS_POR_LAB:
            lab = self._buscar_laboratorio(candidatos, laboratorios)
            if lab is None:
                self.stdout.write(self.style.WARNING(
                    f"Laboratorio no encontrado ({' / '.join(candidatos)}); se omiten: {', '.join(cursos)}"
                ))
                continue

            for nombre in cursos:
                codigo = codigos[nombre]
                curso, creado = Curso.objects.get_or_create(
                    codigo=codigo,
                    defaults={
                        'nombre': nombre,
                        'profesor': profesores[indice_profesor % len(profesores)],
                        'cantidad_estudiantes': random.randint(20, 50),
                        'laboratorio': lab,
                    },
                )
                if creado:
                    indice_profesor += 1
                    creados += 1
                    self.stdout.write(f"  + {curso.codigo} {curso.nombre} -> {lab.nombre}")
                elif curso.laboratorio_id != lab.id:
                    curso.laboratorio = lab
                    curso.save(update_fields=['laboratorio'])
                    actualizados += 1
                    self.stdout.write(f"  ~ {curso.codigo} {curso.nombre} -> {lab.nombre}")
                else:
                    sin_cambios += 1

        self.stdout.write(self.style.SUCCESS(
            f"Cursos creados: {creados} | laboratorio actualizado: {actualizados} | sin cambios: {sin_cambios}"
        ))
