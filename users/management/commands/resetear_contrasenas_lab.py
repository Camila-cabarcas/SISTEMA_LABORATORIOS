"""
resetear_contrasenas_lab.py — users
Management command de un solo uso para resetear la contraseña de las
cuentas de laboratorio (lab_mecanica, lab_test, lab_ondas, lab_sistemas) a
una contraseña compartida simple, y volcar las credenciales resultantes a
CREDENCIALES_LAB.txt en la raíz del proyecto para entregárselas a cada
laboratorista.

SOLO PARA DESARROLLO/DEMO — no correr esto contra una base de datos de
producción real: una contraseña compartida y predecible ('123456') para
varias cuentas con permisos reales (rol='Laboratorio', pueden aprobar/
cancelar reservas, editar insumos, crear préstamos de su laboratorio) es
justo lo que un atacante probaría primero. CREDENCIALES_LAB.txt queda
gitignoreado (ver .gitignore) para que nunca se commitee, pero sigue siendo
texto plano en disco — bórralo apenas se distribuyan las contraseñas.
"""
from django.conf import settings
from django.core.management.base import BaseCommand

from users.models import Usuario

CUENTAS = ['lab_mecanica', 'lab_test', 'lab_ondas', 'lab_sistemas']
CONTRASENA_COMUN = '123456'


class Command(BaseCommand):

    help = (
        'Resetea la contraseña de las cuentas de laboratorio a una contraseña '
        'compartida simple (SOLO desarrollo/demo) y la vuelca a CREDENCIALES_LAB.txt.'
    )

    def handle(self, *args, **kwargs):
        # Sin emoji en stdout a propósito: la consola de Windows por default
        # usa un codepage (cp1252) que no los puede codificar y el comando
        # aborta a mitad de camino con UnicodeEncodeError. El archivo .txt sí
        # se escribe con encoding='utf-8' explícito, así que ahí no hay
        # problema — el emoji solo se evita en las líneas impresas acá.
        self.stdout.write('=== RESETEAR CONTRASENAS LAB ===\n')

        credenciales = []
        faltantes = []

        for username in CUENTAS:
            try:
                user = Usuario.objects.get(username=username)
            except Usuario.DoesNotExist:
                faltantes.append(username)
                self.stdout.write(self.style.WARNING(f'AVISO {username}: no existe, se omite'))
                continue

            user.set_password(CONTRASENA_COMUN)
            user.save(update_fields=['password'])

            credenciales.append({
                'username': username,
                'email': user.email,
                'password': CONTRASENA_COMUN,
            })

            self.stdout.write(self.style.SUCCESS(f'OK {username}'))
            self.stdout.write(f'   Email: {user.email or "(sin email)"}')
            self.stdout.write(f'   Contrasena: {CONTRASENA_COMUN}\n')

        ruta = settings.BASE_DIR / 'CREDENCIALES_LAB.txt'
        with open(ruta, 'w', encoding='utf-8') as f:
            f.write('=== CREDENCIALES DE LABORATORIOS ===\n\n')
            f.write('ADVERTENCIA: DESARROLLO - Contraseñas simples. NO usar en producción.\n\n')
            for cred in credenciales:
                f.write(f"Laboratorio: {cred['username']}\n")
                f.write(f"Email: {cred['email'] or '(sin email)'}\n")
                f.write(f"Contraseña: {cred['password']}\n\n")

        self.stdout.write(self.style.SUCCESS(f'\nOK Credenciales guardadas en {ruta}'))
        self.stdout.write(self.style.WARNING('AVISO Este archivo es solo para desarrollo'))
        self.stdout.write(self.style.WARNING('AVISO Ya esta en .gitignore - NO lo commitees igual a mano'))
        if faltantes:
            self.stdout.write(self.style.WARNING(
                f'AVISO Cuentas no encontradas (omitidas): {", ".join(faltantes)}'
            ))
