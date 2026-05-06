import requests, json

codes = ['HK.00700', 'HK.00005', 'HK.00288', 'HK.02800']
for code in codes:
    r = requests.get(f'http://localhost:5000/api/fundamental/{code}')
    d = r.json()
    div = d.get('data', {}).get('dividend', {})
    print(f"{code}: ttm_yield={div.get('ttm_yield', 'N/A')}")
    print(f"  details={json.dumps(div.get('details', {}), ensure_ascii=False)}")
    print()
