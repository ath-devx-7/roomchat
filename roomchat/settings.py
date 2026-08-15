"""
Django settings for roomchat project.
"""

from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file
load_dotenv(BASE_DIR / '.env')

SECRET_KEY = os.environ.get('SECRET_KEY')

DEBUG = os.environ.get('DEBUG') == 'True'

ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '').split(',') if os.environ.get('ALLOWED_HOSTS') else []

CSRF_TRUSTED_ORIGINS = [o for o in os.environ.get('CSRF_TRUSTED_ORIGINS', '').split(',') if o]

# Render only knows the public hostname once the service exists, so it cannot be written
# into render.yaml. Trusting it here is what keeps ALLOWED_HOSTS off '*' in production.
RENDER_EXTERNAL_HOSTNAME = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
if RENDER_EXTERNAL_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)
    CSRF_TRUSTED_ORIGINS.append(f'https://{RENDER_EXTERNAL_HOSTNAME}')

if not DEBUG:
    # TLS terminates at the platform proxy, so without this Django sees every request as
    # plain HTTP: request.is_secure() stays False and the two secure-cookie flags below
    # would drop the session cookie on every response.
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

INSTALLED_APPS = [
    'daphne',
    'channels',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'accounts',
    'rooms',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'roomchat.middleware.PydanticValidationErrorMiddleware',
]

ROOT_URLCONF = 'roomchat.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'roomchat.wsgi.application'
ASGI_APPLICATION = 'roomchat.asgi.application'

REDIS_URL = os.environ.get('REDIS_URL', 'redis://127.0.0.1:6379/0')

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.pubsub.RedisPubSubChannelLayer',
        'CONFIG': {
            'hosts': [REDIS_URL],
        },
    },
}

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME'),
        'USER': os.environ.get('DB_USER'),
        'PASSWORD': os.environ.get('DB_PASSWORD'),
        'HOST': os.environ.get('DB_HOST', '127.0.0.1'),
        'PORT': os.environ.get('DB_PORT', '5432'),
        # Every ORM call in the consumers runs through database_sync_to_async on a thread
        # pool thread; without persistent connections each one costs a fresh Postgres
        # connect/teardown.
        'CONN_MAX_AGE': 600,
        'CONN_HEALTH_CHECKS': True,
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

# Django 6 dropped STATICFILES_STORAGE; STORAGES is the only form that takes effect.
# WhiteNoise serves collected files directly from the ASGI process, so no CDN or
# separate static host is needed.
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
}

# Routing after sign-in is the SPA's job now; these only still matter to django.contrib.admin.
# API views use roomchat.errors.api_login_required, which answers 401 instead of redirecting.
LOGIN_URL = '/login'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
