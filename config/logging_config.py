"""
logging_config.py — config
Configuración mínima de logging del proyecto: escribe en logs/app.log con
rotación para no saturar el archivo.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
LOGS_DIR = BASE_DIR / 'logs'
os.makedirs(LOGS_DIR, exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'estandar': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'archivo': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'app.log',
            'maxBytes': 5 * 1024 * 1024,  # 5 MB
            'backupCount': 5,
            'formatter': 'estandar',
            'encoding': 'utf-8',
        },
    },
    'root': {
        'handlers': ['archivo'],
        'level': 'INFO',
    },
}
