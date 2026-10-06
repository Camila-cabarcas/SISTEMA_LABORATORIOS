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

# --- CONFIGURACIÓN DE SEGURIDAD (Aquí estaba el error) ---
# DEBUG = True es para desarrollo. Si lo pones en False, debes configurar ALLOWED_HOSTS.
DEBUG = True

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

ALLOWED_HOSTS = ['localhost', '127.0.0.1']
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
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

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
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Base de datos (Por defecto SQLite)
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
# STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles') # Para producción

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_USER_MODEL = 'users.Usuario'

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
SENDGRID_SANDBOX_MODE_IN_DEBUG = False
EMAIL_BACKEND = 'sendgrid_backend.SendgridBackend'
SENDGRID_API_KEY = os.environ.get('SENDGRID_API_KEY', '')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'noreply@sistemalaboratorios.com')

