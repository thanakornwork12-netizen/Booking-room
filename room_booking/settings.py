import os
import dj_database_url
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv

# ---------------- BASE ----------------
BASE_DIR = Path(__file__).resolve().parent.parent

# โหลดค่าจาก .env (ถ้ามี) — สำหรับตั้งค่าเฉพาะเครื่อง เช่น DATABASE_URL ตอน
# dev local ไม่มีผลตอน production (Render ตั้ง env var ของตัวเองอยู่แล้ว
# ไม่มีไฟล์ .env บนนั้น โค้ดนี้แค่ no-op เฉยๆ)
load_dotenv(BASE_DIR / '.env')

# ความปลอดภัย: ใน Production ควรดึงจาก Environment Variable
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-@top1u7dv$mxn%oyw!03)+xq*5nms@isl&bkfvi9lt=o141)sd')

# จะ True เมื่อรันในเครื่อง (localhost) และเป็น False เมื่อรันบน Server (Render)
DEBUG = os.environ.get('DEBUG', 'True') == 'True'

# NOTE: เคยลองบังคับ WSGIRequestHandler.protocol_version = "HTTP/1.0" ตรงนี้
# เพื่อแก้ "Broken pipe" ตอน LDAP ช้า (connection ถูก reuse ผิดจังหวะ) แต่
# พอ LDAP เร็วขึ้นแล้ว (แก้ที่ ldap_auth.py ให้ต่อ port 389 แทน 636) กลับพบว่า
# HTTP/1.0 ทำให้ browser รอ response ค้างจนกว่า axios timeout (15s) แทน —
# น่าจะเป็นเพราะ HTTP/1.0 ให้ browser ยึด "server ปิด connection" เป็นสัญญาณ
# จบ response แทนที่จะเชื่อ Content-Length อย่างเดียว แต่ runserver ปิด
# connection ไม่ตรงจังหวะพอ เลยเอาออก ปล่อยเป็น default (HTTP/1.1) ตามเดิม
TIME_ZONE = 'Asia/Bangkok'
USE_TZ    = True
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
    'django_extensions', 
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
    'https://room-booking-1-7u7e.onrender.com', # Frontend บน Render
]
# อนุญาตทุกพอร์ตของ localhost/127.0.0.1 เพราะ Vite dev server เปลี่ยนพอร์ตอัตโนมัติ
# เมื่อพอร์ตเดิม (5173) ถูกใช้งานอยู่แล้ว (เช่นรันหลายรอบพร้อมกัน)
CORS_ALLOWED_ORIGIN_REGEXES = [
    r'^http://localhost:\d+$',
    r'^http://127\.0\.0\.1:\d+$',
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
EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')

EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.gmail.com')

EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))

EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True') == 'True'
EMAIL_USE_SSL = os.environ.get('EMAIL_USE_SSL', 'False') == 'True'
EMAIL_TIMEOUT = int(os.environ.get('EMAIL_TIMEOUT', '30'))

EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', 'nookkup47@gmail.com')
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER

EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', 'yubm xsqs ndrp sucb')

AUTH_LDAP_SERVER_HOST = '202.28.50.28'
AUTH_LDAP_DOMAIN     = 'UBU'
AUTH_LDAP_BASE_OU    = 'OU=STD,OU=SCI,DC=UBU,DC=AC,DC=TH'
