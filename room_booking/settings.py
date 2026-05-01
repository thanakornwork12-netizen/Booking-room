import os
import dj_database_url
from pathlib import Path
from datetime import timedelta

# ---------------- BASE ----------------
BASE_DIR = Path(__file__).resolve().parent.parent

# ความปลอดภัย: ใน Production ควรดึงจาก Environment Variable
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-@top1u7dv$mxn%oyw!03)+xq*5nms@isl&bkfvi9lt=o141)sd')

# จะ True เมื่อรันในเครื่อง (localhost) และเป็น False เมื่อรันบน Server (Render)
DEBUG = os.environ.get('DEBUG', 'True') == 'True'

# ระบุ Domain ที่อนุญาตให้เข้าถึง
ALLOWED_HOSTS = ['room-booking-1-7u7e.onrender.com', 'localhost', '127.0.0.1', '*']

# ---------------- INSTALLED APPS ----------------
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # third party
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    'channels',
    'django_apscheduler',
    'import_export',
    # local apps
    'booking',
]

APSCHEDULER_DATETIME_FORMAT = "N j, Y, f:s a"
APSCHEDULER_RUN_NOW_TIMEOUT = 25

# ---------------- MIDDLEWARE ----------------
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',  # ต้องอยู่บนสุด
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware', # เพิ่มจัดการไฟล์ static บน server
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'room_booking.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
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

# ---------------- WSGI / ASGI ----------------
WSGI_APPLICATION = 'room_booking.wsgi.application'
ASGI_APPLICATION = 'room_booking.asgi.application'

# ---------------- DATABASE (แก้ไขให้ถาวร) ----------------
# ค่าเริ่มต้นสำหรับ localhost (ข้อมูลเก็บในไฟล์ db.sqlite3)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# หากรันบน Render หรือที่ที่มี DATABASE_URL (เช่น Postgres) ให้ใช้ค่านี้แทนอัตโนมัติ
# ข้อมูลจะอยู่ถาวรบน PostgreSQL ไม่หายเวลา Restart
if os.environ.get('DATABASE_URL'):
    DATABASES['default'] = dj_database_url.config(
        default=os.environ.get('DATABASE_URL'),
        conn_max_age=600,
        conn_health_checks=True,
    )

# ---------------- CORS ----------------
CORS_ALLOWED_ORIGINS = [
    'http://localhost:5173',
    'http://127.0.0.1:5173',
    'https://room-booking-1-7u7e.onrender.com', # Frontend บน Render
]
CORS_ALLOW_CREDENTIALS = True

# ---------------- AUTH ----------------
AUTH_USER_MODEL = 'booking.User'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ---------------- CHANNELS ----------------
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    }
}

# ---------------- INTERNATIONALIZATION ----------------
LANGUAGE_CODE = 'th'
TIME_ZONE = 'Asia/Bangkok'
USE_I18N = True
USE_TZ = True

# ---------------- STATIC & MEDIA ----------------
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles' # สำหรับ Production
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ---------------- DJANGO REST FRAMEWORK ----------------
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}

# ---------------- JWT (ปรับให้ Token อายุยาวขึ้น ไม่หลุดบ่อย) ----------------
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=1),   # ใช้งานได้ต่อเนื่อง 1 วัน
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30), # อยู่ได้ยาว 30 วัน
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': False,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
}
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'

EMAIL_HOST = 'smtp.gmail.com'

EMAIL_PORT = 587

EMAIL_USE_TLS = True

EMAIL_HOST_USER = 'nookkup47@gmail.com'

EMAIL_HOST_PASSWORD = 'yubm xsqs ndrp sucb'

