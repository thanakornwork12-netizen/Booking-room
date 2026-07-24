import json
import datetime
from ldap3 import Server, Connection, ALL, SUBTREE, NTLM
from django.conf import settings


def authenticate_ldap(username: str, password: str) -> dict | None:
    """
    รับ username (รหัสนศ) และ password จาก user จริง
    คืนค่า dict ข้อมูลนศ ถ้า login สำเร็จ หรือ None ถ้าล้มเหลว
    """
    server = Server(
        settings.AUTH_LDAP_SERVER_URI,
        get_info=ALL,
        use_ssl=True
    )

    domain = settings.AUTH_LDAP_DOMAIN
    candidate_principals = [
        f"{domain}\\{username}",
        f"{username}@{domain.lower()}.ac.th",
        username,
    ]

    conn = None
    last_error = None

    # Only use SIMPLE bind for this LDAP server.
    for bind_dn in candidate_principals:
        try:
            print(f'[LDAP] trying bind DN: {bind_dn} with SIMPLE')
            conn = Connection(
                server,
                user=bind_dn,
                password=password,
                auto_bind=True,
            )
            if conn.bound:
                print(f'[LDAP] bind success: {bind_dn} with SIMPLE')
                break
        except Exception as e:
            last_error = e
            print(f'[LDAP] bind failed for {bind_dn} with SIMPLE: {e}')
            conn = None

    if not conn or not conn.bound:
        print(f'[LDAP] ERROR: all bind attempts failed - {last_error}')
        return None

    year_prefix = username[:2]
    search_base = (
        f'CN={username},'
        f'OU={year_prefix},'
        f'{settings.AUTH_LDAP_BASE_OU}'
    )

    conn.search(
        search_base=search_base,
        search_filter='(objectCategory=user)',
        search_scope=SUBTREE,
        attributes=['*']   # ดึงทุก field เพื่อให้เห็นว่ามีอะไรบ้าง
    )

    if conn.entries:
        entry = conn.entries[0]

        # ── Log ทุก field ที่ LDAP ส่งมา (ดูใน terminal) ──────────────
        print('\n' + '='*60)
        print('[LDAP] RAW ATTRIBUTES ทั้งหมด:')
        print(json.dumps(
            {k: str(v) for k, v in entry.entry_attributes_as_dict.items()},
            ensure_ascii=False,
            indent=2
        ))
        print('='*60 + '\n')
        # ──────────────────────────────────────────────────────────────

        # ── ดึง field ที่ต้องการ (ใช้ .value เพื่อป้องกัน error) ──────
        def get(attr):
            try:
                val = getattr(entry, attr).value
                return str(val) if val else ''
            except Exception:
                return ''

        result = {
            'username':    username,
            'full_name':   get('displayName'),
            'email':       get('mail'),
            'department':  get('department'),                  # คณะ
            'branch':      get('physicalDeliveryOfficeName'),  # สาขา (ถ้ามี)
            'title':       get('title'),                       # สถานะ เช่น นักศึกษา
            'employee_id': get('employeeID'),                  # รหัสนศ จาก LDAP
            'ou':          get('ou'),                          # หน่วยงาน
            'description': get('description'),                 # คำอธิบายเพิ่มเติม
            'company':     get('company'),                     # มหาวิทยาลัย
        }

        # ── Log ข้อมูลที่ parse แล้ว ───────────────────────────────────
        print('[LDAP] LOGIN SUCCESS:')
        print(json.dumps(
            {**result, 'time': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')},
            ensure_ascii=False,
            indent=2
        ))

        conn.unbind()
        return result

    conn.unbind()
    return None