import argparse
import json
from ldap3 import Server, Connection, ALL, SUBTREE


LDAP_SERVER_URL = 'ldap://202.28.50.28'
LDAP_DOMAIN = 'UBU'
LDAP_ROOT_BASE = 'DC=UBU,DC=AC,DC=TH'
LDAP_STUDENT_BASE_TEMPLATE = 'CN={username},OU={year_prefix},OU=STD,OU=SCI,DC=UBU,DC=AC,DC=TH'


def safe_get(entry, attr):
    try:
        value = getattr(entry, attr).value
        return str(value) if value else ''
    except Exception:
        return ''


def print_entry(entry, label):
    print(f'\n--- {label} ---')
    print(f'DN: {entry.entry_dn}')
    print(json.dumps(
        {k: str(v) for k, v in entry.entry_attributes_as_dict.items()},
        ensure_ascii=False,
        indent=2,
    ))
    print(
        'สรุป role จาก DN:',
        'student' if 'OU=STD' in entry.entry_dn.upper() else 'not_student_or_possibly_staff'
    )
    print(
        'title:', safe_get(entry, 'title') or '-',
        '| department:', safe_get(entry, 'department') or '-',
        '| ou:', safe_get(entry, 'ou') or '-',
    )


def main():
    parser = argparse.ArgumentParser(description='LDAP test for student/staff/lecturer accounts')
    parser.add_argument('username', help='รหัสผู้ใช้ เช่น รหัสนศ หรือรหัสอาจารย์')
    parser.add_argument('password', help='รหัสผ่าน')
    args = parser.parse_args()

    username = args.username.strip()
    password = args.password
    pure_username = username.split('@')[0]
    year_prefix = pure_username[:2]

    server = Server(LDAP_SERVER_URL, get_info=ALL)
    candidate_principals = [
        f'{LDAP_DOMAIN}\\{pure_username}',
        f'{pure_username}@{LDAP_DOMAIN.lower()}.ac.th',
        pure_username,
    ]

    conn = None
    last_error = None

    print(f'กำลังเชื่อมต่อ {LDAP_SERVER_URL} ...')
    for bind_dn in candidate_principals:
        try:
            print(f'ลอง bind ด้วย: {bind_dn}')
            conn = Connection(server, user=bind_dn, password=password, auto_bind=True)
            if conn.bound:
                print(f'bind สำเร็จ: {bind_dn}')
                break
        except Exception as exc:
            last_error = exc
            print(f'bind ไม่ผ่าน: {exc}')
            conn = None

    if not conn or not conn.bound:
        print('Bind ล้มเหลวทั้งหมด')
        if last_error:
            print(f'สาเหตุล่าสุด: {last_error}')
        return

    student_base = LDAP_STUDENT_BASE_TEMPLATE.format(username=pure_username, year_prefix=year_prefix)
    search_filter = f'(|(sAMAccountName={pure_username})(userPrincipalName={pure_username}@ubu.ac.th)(cn={pure_username}))'

    print('\nค้นหาแบบฐานนักศึกษา...')
    conn.search(
        search_base=student_base,
        search_filter=search_filter,
        search_scope=SUBTREE,
        attributes=['*'],
    )
    if conn.entries:
        print_entry(conn.entries[0], 'พบในฐานนักศึกษา')
    else:
        print('ไม่พบในฐานนักศึกษา')

    print('\nค้นหาแบบฐานกลางโดเมน...')
    conn.search(
        search_base=LDAP_ROOT_BASE,
        search_filter=search_filter,
        search_scope=SUBTREE,
        attributes=['*'],
    )
    if conn.entries:
        print_entry(conn.entries[0], 'พบในฐานกลางโดเมน')
    else:
        print('ไม่พบในฐานกลางโดเมน')

    conn.unbind()
    print('\nปิดการเชื่อมต่อแล้ว')


if __name__ == '__main__':
    main()
