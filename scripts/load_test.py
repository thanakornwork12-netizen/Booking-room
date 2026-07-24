#!/usr/bin/env python3
"""
ทดสอบการรองรับ Concurrent Users — จองพร้อมกันหลาย request

วิธีใช้:
  python scripts/load_test.py --url http://127.0.0.1:8000 --users 20 --token YOUR_JWT

ต้องมี user ที่ login แล้ว (JWT) และมีห้องว่างในช่วงเวลาที่ทดสอบ
"""

import argparse
import concurrent.futures
import time
from datetime import date, datetime, timedelta
from collections import Counter

try:
    import requests
except ImportError:
    print('pip install requests')
    raise


def one_booking(base_url: str, token: str, room_id: int, idx: int, kind: str, payload: dict) -> dict:
    headers = {'Authorization': f'Bearer {token}'}
    endpoint = '/api/bookings/'
    body = dict(payload)
    if kind == 'term':
        endpoint = '/api/term-bookings/'
        body.setdefault('room', room_id)
    else:
        body.setdefault('room', room_id)

    t0 = time.perf_counter()
    try:
        r = requests.post(f'{base_url}{endpoint}', json=body, headers=headers, timeout=30)
        elapsed = time.perf_counter() - t0
        return {'idx': idx, 'status': r.status_code, 'elapsed': elapsed, 'ok': r.status_code in (200, 201)}
    except Exception as e:
        return {'idx': idx, 'status': 0, 'elapsed': time.perf_counter() - t0, 'ok': False, 'error': str(e)}


def build_payload(kind: str, room_id: int, same_slot: bool, idx: int, args) -> dict:
    if kind == 'term':
        base_date = date.fromisoformat(args.term_start)
        end_date = date.fromisoformat(args.term_end)
        if not same_slot:
          # กระจายวันแบบเบา ๆ ถ้าต้องการลองหลายเคส
          base_date = base_date + timedelta(days=idx % 3)
          end_date = max(base_date + timedelta(days=30), end_date)
        return {
            'room': room_id,
            'subject_name': args.subject_name,
            'attendees': args.attendees,
            'day_of_week': args.day_of_week,
            'start_time': args.start_time,
            'end_time': args.end_time,
            'term_start': str(base_date),
            'term_end': str(end_date),
            'term_name': args.term_name,
            'note': 'concurrent load test',
        }

    booking_date = date.fromisoformat(args.date)
    if not same_slot:
        booking_date = booking_date + timedelta(days=idx % 3)
    return {
        'room': room_id,
        'title': args.title,
        'attendees': args.attendees,
        'start_time': f'{booking_date}T{args.start_time}:00',
        'end_time': f'{booking_date}T{args.end_time}:00',
        'note': 'concurrent load test',
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:8000')
    parser.add_argument('--users', type=int, default=10, help='จำนวน concurrent requests')
    parser.add_argument('--token', required=True, help='JWT access token')
    parser.add_argument('--room', type=int, default=1, help='room id')
    parser.add_argument('--kind', choices=['daily', 'term'], default='daily', help='ชนิดการจองที่ทดสอบ')
    parser.add_argument('--same-slot', action='store_true', help='ให้ทุก request แย่ง slot เดียวกัน')
    parser.add_argument('--date', default=(date.today() + timedelta(days=1)).isoformat(), help='วันที่จองสำหรับ daily')
    parser.add_argument('--start-time', default='09:00', help='เวลาเริ่ม')
    parser.add_argument('--end-time', default='10:00', help='เวลาสิ้นสุด')
    parser.add_argument('--attendees', type=int, default=5, help='จำนวนผู้เข้าร่วม')
    parser.add_argument('--title', default='Load test booking', help='หัวข้อการจองรายวัน')
    parser.add_argument('--subject-name', default='Load test subject', help='ชื่อวิชา/กิจกรรมสำหรับ term')
    parser.add_argument('--term-start', default=(date.today() + timedelta(days=1)).isoformat(), help='วันเริ่มเทอมสำหรับ term')
    parser.add_argument('--term-end', default=(date.today() + timedelta(days=90)).isoformat(), help='วันสิ้นสุดเทอมสำหรับ term')
    parser.add_argument('--day-of-week', type=int, default=(date.today() + timedelta(days=1)).weekday(), help='0=จันทร์ ... 6=อาทิตย์')
    parser.add_argument('--term-name', default='LoadTest/2569', help='ชื่อเทอม')
    args = parser.parse_args()

    print(f'🚀 Load test: {args.users} concurrent {args.kind} bookings → {args.url}')
    t0 = time.perf_counter()

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.users) as ex:
        futures = [
            ex.submit(
                one_booking,
                args.url,
                args.token,
                args.room,
                i,
                args.kind,
                build_payload(args.kind, args.room, args.same_slot, i, args),
            )
            for i in range(args.users)
        ]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    total = time.perf_counter() - t0
    ok    = sum(1 for r in results if r['ok'])
    times = [r['elapsed'] for r in results]
    codes = Counter(r['status'] for r in results)

    print(f'\n📊 ผลลัพธ์ ({total:.2f}s รวม)')
    print(f'   สำเร็จ: {ok}/{args.users}')
    print(f'   HTTP codes: {dict(sorted(codes.items()))}')
    print(f'   Response time — min: {min(times):.3f}s | avg: {sum(times)/len(times):.3f}s | max: {max(times):.3f}s')
    for r in sorted(results, key=lambda x: x['idx'])[:5]:
        print(f"   #{r['idx']}: HTTP {r['status']} ({r['elapsed']:.3f}s)")
    if args.users > 5:
        print(f'   ... และอีก {args.users - 5} requests')


if __name__ == '__main__':
    main()
