import requests, json

# 看完整 dividend 结构
r = requests.get('http://localhost:5000/api/fundamental/HK.00700')
d = r.json().get('data', {})
div = d.get('dividend', {})
print("=== dividend 顶层 ===")
print(f"ttm_yield: {div.get('ttm_yield')}")
print(f"score: {div.get('score')}")
print()
print("=== dividend.details ===")
details = div.get('details', {})
for k, v in details.items():
    print(f"  {k}: {v}")
