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
from datetime import datetime, timedelta

try:
    import requests
except ImportError:
    print('pip install requests')
    raise


def one_booking(base_url: str, token: str, room_id: int, idx: int) -> dict:
    start = datetime.now() + timedelta(days=1, hours=idx % 8 + 8)
    end   = start + timedelta(hours=1)
    headers = {'Authorization': f'Bearer {token}'}
    payload = {
        'room': room_id,
        'title': f'Load test #{idx}',
        'attendees': 5,
        'start_time': start.strftime('%Y-%m-%dT%H:%M:%S'),
        'end_time': end.strftime('%Y-%m-%dT%H:%M:%S'),
    }
    t0 = time.perf_counter()
    try:
        r = requests.post(f'{base_url}/api/bookings/', json=payload, headers=headers, timeout=30)
        elapsed = time.perf_counter() - t0
        return {'idx': idx, 'status': r.status_code, 'elapsed': elapsed, 'ok': r.status_code in (200, 201)}
    except Exception as e:
        return {'idx': idx, 'status': 0, 'elapsed': time.perf_counter() - t0, 'ok': False, 'error': str(e)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:8000')
    parser.add_argument('--users', type=int, default=10, help='จำนวน concurrent requests')
    parser.add_argument('--token', required=True, help='JWT access token')
    parser.add_argument('--room', type=int, default=1, help='room id')
    args = parser.parse_args()

    print(f'🚀 Load test: {args.users} concurrent bookings → {args.url}')
    t0 = time.perf_counter()

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.users) as ex:
        futures = [ex.submit(one_booking, args.url, args.token, args.room, i) for i in range(args.users)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    total = time.perf_counter() - t0
    ok    = sum(1 for r in results if r['ok'])
    times = [r['elapsed'] for r in results]

    print(f'\n📊 ผลลัพธ์ ({total:.2f}s รวม)')
    print(f'   สำเร็จ: {ok}/{args.users}')
    print(f'   Response time — min: {min(times):.3f}s | avg: {sum(times)/len(times):.3f}s | max: {max(times):.3f}s')
    for r in sorted(results, key=lambda x: x['idx'])[:5]:
        print(f"   #{r['idx']}: HTTP {r['status']} ({r['elapsed']:.3f}s)")
    if args.users > 5:
        print(f'   ... และอีก {args.users - 5} requests')


if __name__ == '__main__':
    main()
