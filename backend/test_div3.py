import requests, json

# 测试批量：哪些有 details，哪些没有
codes = ['HK.00700', 'HK.00005', 'HK.00288', 'HK.02800', 'HK.00941', 'HK.02318']
for code in codes:
    r = requests.get(f'http://localhost:5000/api/fundamental/{code}')
    d = r.json().get('data', {})
    div = d.get('dividend', {})
    details = div.get('details', {})
    div_yield = details.get('股息率', 'MISSING')
    div_realtime = details.get('股息率_实时', 'NONE')
    print(f"{code}: details_keys={list(details.keys())}")
    print(f"  股息率={div_yield}, 股息率_实时={div_realtime}")
    print()
