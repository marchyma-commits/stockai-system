import json

# 直接读 cache 看看 summary 里面的 股息率
codes = {
    'HK.00700': 'C:/Users/MarcoMa/stockai_data/cache/00700_financial.json',
    'HK.00005': 'C:/Users/MarcoMa/stockai_data/cache/00005_financial.json',
    'HK.00288': 'C:/Users/MarcoMa/stockai_data/cache/00288_financial.json',
    'HK.02800': 'C:/Users/MarcoMa/stockai_data/cache/02800_financial.json',
}

for code, path in codes.items():
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        summary = data.get('financial_summary', {})
        div = summary.get('股息率', 'MISSING')
        div_rt = summary.get('股息率_实时', 'NONE')
        payout = summary.get('派息率', 'MISSING')
        print(f"{code}: 股息率={div}, 股息率_实时={div_rt}, 派息率={payout}")
    except Exception as e:
        print(f"{code}: ERROR - {e}")
