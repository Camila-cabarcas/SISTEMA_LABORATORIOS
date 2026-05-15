# Internationalization
LANGUAGE_CODE = 'es-co'

TIME_ZONE = 'America/Bogota'

USE_I18N = True

USE_TZ = False  # Ya desinstalaste tzdata, mejor en False

LANGUAGES = [
    ('es', 'Spanish'),
    ('en', 'English'),
]

# Static files
STATIC_URL = 'static/'

LOGIN_URL = '/admin/login/'