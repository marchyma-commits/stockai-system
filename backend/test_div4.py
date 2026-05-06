import requests, json

# 看 health_check 的结果
codes = ['HK.00700', 'HK.00005', 'HK.02800']
for code in codes:
    r = requests.get(f'http://localhost:5000/api/fundamental/{code}')
    d = r.json().get('data', {})
    hc = d.get('health_check', {})
    checks = hc.get('checks', [])
    print(f"=== {code} ===")
    for c in checks:
        if '股息' in c.get('name', ''):
            print(f"  {c['name']}: status={c['status']}, value={c['value']}, detail={c['detail']}")
    print()
