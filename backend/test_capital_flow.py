"""测试富途 get_capital_flow / get_capital_distribution 接口"""
from futu import *
import sys

quote_ctx = OpenQuoteContext(host='127.0.0.1', port=11111)

# 测试1: 资金流向 (实时)
print('=== Test 1: get_capital_flow (HK.00700 INTRADAY) ===')
ret, data = quote_ctx.get_capital_flow('HK.00700', period_type=PeriodType.INTRADAY)
if ret == RET_OK:
    print('SUCCESS!')
    print(data.tail(5))
    print('Columns:', list(data.columns))
else:
    print('FAILED:', data)

print()

# 测试2: 资金分布
print('=== Test 2: get_capital_distribution (HK.00700) ===')
ret, data = quote_ctx.get_capital_distribution('HK.00700')
if ret == RET_OK:
    print('SUCCESS!')
    print(data)
    print('Columns:', list(data.columns))
else:
    print('FAILED:', data)

quote_ctx.close()
print('\nDone.')
