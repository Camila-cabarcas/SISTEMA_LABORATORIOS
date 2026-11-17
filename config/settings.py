import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

# Construye las rutas dentro del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent

# Carga variables desde .env (no versionado — ver .env.example) antes de
# leerlas más abajo. Secretos como SENDGRID_API_KEY y SECRET_KEY NUNCA van
# hardcodeados acá: este archivo sí se commitea a git.
load_dotenv(BASE_DIR / '.env')


def _env_bool(nombre, por_defecto):
    """Lee una variable de entorno booleana ('true'/'1'/'yes'/'on' = True)."""
    valor = os.getenv(nombre)
    if valor is None or valor.strip() == '':
        return por_defecto
    return valor.strip().lower() in ('1', 'true', 'yes', 'on', 'si', 'sí')


def _env_lista(nombre, por_defecto):
    """Lee una variable de entorno separada por comas, sin espacios ni vacíos."""
    valor = os.getenv(nombre)
    if valor is None or valor.strip() == '':
        return list(por_defecto)
    return [item.strip() for item in valor.split(',') if item.strip()]


# --- CONFIGURACIÓN DE SEGURIDAD ---
# DEBUG viene de .env (por defecto True, para desarrollo). En el servidor de
# producción va DEBUG=False, y entonces ALLOWED_HOSTS debe incluir la IP o el
# nombre con el que se accede al sitio.
DEBUG = _env_bool('DEBUG', True)

# SECRET_KEY vive en .env (ver .env.example) — nunca hardcodeada acá. Antes
# había una acá mismo ('django-insecure-...'), que quedó expuesta para
# siempre en el historial de git en cuanto se commiteó; se rotó y se movió
# a .env. Falla fuerte (en vez de caer a un default inseguro) si falta,
# para que un despliegue sin .env configurado no arranque en silencio con
# una clave predecible.
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    raise ImproperlyConfigured(
        "SECRET_KEY no definida. Agrégala a tu .env (ver .env.example) — "
        "genera una con: python -c \"from django.core.management.utils "
        "import get_random_secret_key; print(get_random_secret_key())\""
    )

# Separado por comas en .env, p. ej. ALLOWED_HOSTS=172.21.35.40,localhost
ALLOWED_HOSTS = _env_lista('ALLOWED_HOSTS', ['localhost', '127.0.0.1'])
# ---------------------------------------------------------

# Aplicaciones instaladas
INSTALLED_APPS = [
    # admin_interface (y su dependencia colorfield) van ANTES de
    # django.contrib.admin: así sobreescribe las plantillas del admin de
    # Django con las suyas — al revés no tiene efecto.
    'admin_interface',
    'colorfield',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'inventario.apps.InventarioConfig',
    'prestamos.apps.PrestamosConfig',
    'reservas',
    'users',
    'laboratorio',
    'solicitudes',
    'vetos',
    'dashboard',
]

# django-admin-interface muestra la vista previa de temas en un <iframe> del
# propio admin — el XFrameOptionsMiddleware de Django deniega eso por
# defecto (X-Frame-Options: DENY). SAMEORIGIN alcanza porque ese iframe
# siempre carga una URL del mismo sitio, nunca de otro origen.
X_FRAME_OPTIONS = 'SAMEORIGIN'

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # WhiteNoise sirve los archivos de STATIC_ROOT (collectstatic) cuando
    # DEBUG=False y no hay otro servidor web delante de waitress. Va justo
    # después de SecurityMiddleware, como pide su documentación.
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'vetos.middleware.VetosAutomaticosMiddleware',
]

# Cada cuántos minutos, como máximo, VetosAutomaticosMiddleware revisa las
# reservas vencidas sin retirar y crea sus vetos NO_CANCELO (0 = desactivado;
# queda el comando generar_vetos_no_cancelo para correrlo por cron).
VETOS_AUTO_INTERVALO_MINUTOS = 10

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'config.context_processors.notificaciones_admin',
                'config.context_processors.menu_personal',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Base de datos: PostgreSQL si DB_ENGINE=postgres en .env; si no, SQLite como
# siempre. La contraseña (DB_PASSWORD) vive solo en .env, nunca acá.
if os.getenv('DB_ENGINE', '').strip().lower() in ('postgres', 'postgresql'):
    _faltantes = [v for v in ('DB_NAME', 'DB_USER') if not os.getenv(v)]
    if _faltantes:
        raise ImproperlyConfigured(
            "DB_ENGINE=postgres pero faltan en .env: " + ", ".join(_faltantes)
        )
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv('DB_NAME'),
            'USER': os.getenv('DB_USER'),
            'PASSWORD': os.getenv('DB_PASSWORD', ''),
            'HOST': os.getenv('DB_HOST', 'localhost'),
            'PORT': os.getenv('DB_PORT', '5432'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# Internacionalización (Tus ajustes de Colombia)
LANGUAGE_CODE = 'es-co'
TIME_ZONE = 'America/Bogota'
USE_I18N = True
USE_L10N = True
USE_TZ = False  # Como mencionaste que no usas tzdata

LANGUAGES = [
    ('es', 'Spanish'),
    ('en', 'English'),
]

# Archivos Estáticos
STATIC_URL = 'static/'
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]
# Destino de collectstatic; WhiteNoise sirve desde aquí en producción.
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_USER_MODEL = 'users.Usuario'

# Login con usuario o correo (sin distinguir mayúsculas). Hereda de
# ModelBackend, así que reemplaza al backend por defecto sin perder nada.
AUTHENTICATION_BACKENDS = ['users.backends.UsuarioOCorreoBackend']

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'

# El tag por defecto de messages.error() es 'error', pero Bootstrap no
# tiene una clase alert-error — la mapeamos a alert-danger para que
# {{ message.tags }} en base_general.html produzca una clase real.
from django.contrib.messages import constants as message_constants
MESSAGE_TAGS = {
    message_constants.ERROR: 'danger',
}

from .logging_config import LOGGING

# --- Email (SendGrid) --------------------------------------------------
# La API key vive en .env (no versionado — ver .env.example), nunca acá:
# este archivo sí se commitea a git y una key hardcodeada quedaría expuesta
# en el historial para siempre, aunque después se borre de acá.
#
# Sin SENDGRID_API_KEY en el entorno, los correos van al backend de consola:
# se imprimen en la salida del servidor y no le llegan a nadie, sin error.
# Con la key definida, salen de verdad por SendGrid.
SENDGRID_SANDBOX_MODE_IN_DEBUG = False
SENDGRID_API_KEY = os.environ.get('SENDGRID_API_KEY', '').strip()
if SENDGRID_API_KEY:
    EMAIL_BACKEND = 'sendgrid_backend.SendgridBackend'
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'noreply@sistemalaboratorios.com')

