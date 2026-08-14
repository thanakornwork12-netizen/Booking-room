import json
import datetime
from ldap3 import Server, Connection, ALL, SUBTREE, NTLM, AUTO_BIND_TLS_BEFORE_BIND
from ldap3.core.exceptions import LDAPSocketReceiveError, LDAPSocketOpenError
from django.conf import settings


def authenticate_ldap(username: str, password: str, extra_principal: str | None = None) -> dict | None:
    """
    รับ username (รหัสนศ) และ password จาก user จริง
    คืนค่า dict ข้อมูลนศ ถ้า login สำเร็จ หรือ None ถ้าล้มเหลว

    extra_principal: ใช้เมื่อ user กรอกอีเมลจริงของมหาลัย (เช่น
    thanakorn.tho.66@ubu.ac.th) ซึ่งไม่ตรงกับ sAMAccountName ที่เป็นตัวเลข —
    ส่งอีเมลเต็มมาลอง bind ตรงๆ เป็นอีกหนึ่ง candidate (บาง AD config รับ
    mail/UPN แบบนี้ได้)
    """
    # ต่อผ่าน plain LDAP (port 389) + STARTTLS ก่อน bind แทน LDAPS (port 636)
    # ที่ใช้มาแต่แรก — เทียบกับสคริปต์อ้างอิงที่ใช้งานได้จริงแล้วพบว่า
    # server นี้ตอบสนองบน port 389 เร็วมาก (<1s) ในขณะที่ port 636 ตอบช้า/
    # ไม่ตอบเลยเป็นสิบวินาทีแบบไม่คงที่ — เป็นสาเหตุจริงของอาการ timeout
    # ที่เจอมาตลอด ไม่ใช่บัญชีถูก throttle ตามที่เคยสงสัย
    # ยังคง encrypt ด้วย STARTTLS ก่อน bind (server รองรับ) เพื่อไม่ส่ง
    # รหัสผ่านเป็น cleartext ทั้งที่สคริปต์ต้นฉบับไม่ได้เข้ารหัสเลย
    #
    # connect_timeout/receive_timeout ยังตั้งไว้เป็นเซฟตี้เน็ต กัน hang ถ้า
    # server ช้าอีกในอนาคต (ซึ่งควรเป็นสิ่งที่ไม่ควรเกิดแล้วบน port นี้)
    server = Server(
        settings.AUTH_LDAP_SERVER_HOST,
        port=389,
        get_info=ALL,
        use_ssl=False,
        connect_timeout=5,
    )

    domain = settings.AUTH_LDAP_DOMAIN
    candidate_principals = [
        f"{username}@{domain.lower()}.ac.th",   # รูปแบบตามสคริปต์อ้างอิงที่ใช้งานได้จริง — ลองก่อน
        f"{domain}\\{username}",
        username,
    ]
    if extra_principal and extra_principal not in candidate_principals:
        # ลองอีเมลจริงก่อนเป็นอันดับแรก เพราะถ้า user พิมพ์อีเมลมา โอกาสสูง
        # ว่านี่คือรูปแบบที่ตั้งใจใช้ล็อกอินจริง
        candidate_principals.insert(0, extra_principal)

    conn = None
    last_error = None
    bound_dn = None

    # Only use SIMPLE bind for this LDAP server.
    for bind_dn in candidate_principals:
        try:
            print(f'[LDAP] trying bind DN: {bind_dn} with SIMPLE')
            conn = Connection(
                server,
                user=bind_dn,
                password=password,
                auto_bind=AUTO_BIND_TLS_BEFORE_BIND,
                receive_timeout=3,
            )
            if conn.bound:
                print(f'[LDAP] bind success: {bind_dn} with SIMPLE')
                bound_dn = bind_dn
                break
        except (LDAPSocketReceiveError, LDAPSocketOpenError) as e:
            # timeout/connection-level error (ไม่ใช่ invalidCredentials) —
            # แปลว่า LDAP server เองช้า/ไม่ตอบสนองตอนนี้ ไม่ใช่ format ของ
            # bind DN ผิด ลองรูปแบบอื่นต่อก็จะช้าซ้ำแบบเดิม ไม่มีประโยชน์
            # เลิกลองรูปแบบที่เหลือทันทีแทนที่จะรอ timeout ซ้ำ 3 รอบเต็มๆ
            last_error = e
            print(f'[LDAP] bind timed out for {bind_dn} with SIMPLE (server ช้า/ไม่ตอบ): {e}')
            conn = None
            break
        except Exception as e:
            last_error = e
            print(f'[LDAP] bind failed for {bind_dn} with SIMPLE: {e}')
            conn = None

    if not conn or not conn.bound:
        print(f'[LDAP] ERROR: all bind attempts failed - {last_error}')
        return None

    # ── หา entry เพื่อดึงโปรไฟล์ (ชื่อ, อีเมล, คณะ, ...) ────────────────
    # ค้นด้วย filter จาก base OU ที่ตั้งไว้ แทนการเดา DN เป๊ะๆ (เช่น เดาว่า
    # OU ปีคือเลข 2 ตัวแรกของ username) เพราะ bind ข้างบนพิสูจน์แล้วว่า
    # รหัสผ่านถูกต้อง — ถ้าเดา DN ผิด (เช่น account ไม่ได้อยู่ OU ที่คาดไว้)
    # search แบบเดิมจะเจอ 0 entries แล้วทำให้ทั้งฟังก์ชัน return None
    # เหมือนกับรหัสผ่านผิด ทั้งที่ auth ผ่านไปแล้วจริงๆ
    #
    # ถ้า bind สำเร็จผ่าน extra_principal (อีเมลจริง เช่น
    # thanakorn.tho.66@ubu.ac.th) แปลว่า username ที่ได้มาเป็นแค่ local-part
    # ของอีเมล ไม่ใช่ sAMAccountName จริง (ตัวเลข) — ค้นด้วย mail แทน
    if bound_dn == extra_principal:
        search_filter = f'(mail={extra_principal})'
    else:
        search_filter = f'(sAMAccountName={username})'

    conn.search(
        search_base=settings.AUTH_LDAP_BASE_OU,
        search_filter=search_filter,
        search_scope=SUBTREE,
        time_limit=3,
        attributes=['*']   # ดึงทุก field เพื่อให้เห็นว่ามีอะไรบ้าง
    )

    if not conn.entries:
        # bind สำเร็จ = รหัสผ่านถูกต้องแน่นอน แม้หา entry โปรไฟล์ไม่เจอ
        # (เช่น account อยู่นอก OU ที่ตั้งไว้ หรือ attribute ไม่ตรงที่คาด)
        # ก็ยังต้องนับว่า login ผ่าน ไม่ใช่ปนกับ "รหัสผ่านผิด"
        print(f'[LDAP] WARNING: bind succeeded for {username} but no profile entry found under {settings.AUTH_LDAP_BASE_OU}')
        conn.unbind()
        return {
            'username': username, 'full_name': '', 'email': '', 'department': '',
            'branch': '', 'title': '', 'employee_id': username, 'ou': '', 'description': '', 'company': '',
        }

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

    # ใช้ sAMAccountName จริงจาก entry เป็น username หลักเสมอ (ไม่ใช่ local-part
    # ที่เดาจากอีเมล) กัน Django User ซ้ำ 2 คนจากคนเดียวกันที่ล็อกอินด้วย
    # อีเมลบ้าง รหัสนักศึกษาบ้าง
    real_username = get('sAMAccountName') or username

    result = {
        'username':    real_username,
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