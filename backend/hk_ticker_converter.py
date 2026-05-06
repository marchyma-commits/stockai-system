"""
港股代码转换器
将港股代码 (如 00005.HK) 转换为 TradingView / Yahoo Finance 格式
"""

import json
import os
from typing import Optional

class HKTickerConverter:
    """港股代码转换器"""

    def __init__(self, mapping_path: Optional[str] = None):
        """
        初始化转换器
        Args:
            mapping_path: 港股代码映射表路径
        """
        if mapping_path is None:
            mapping_path = os.path.join(
                os.path.dirname(__file__), '..', 'stockai_data', 'hk_ticker_mapping.json'
            )

        self.mapping_path = mapping_path
        self.mapping = self._load_mapping()

    def _load_mapping(self) -> dict:
        """加载港股代码映射表"""
        default_mapping = {
            # 主要蓝筹股
            '00005': {'yahoo': '0005.HK', 'tradingview': 'HKEX:0005', 'name': '匯豐控股'},
            '00700': {'yahoo': '0700.HK', 'tradingview': 'HKEX:0700', 'name': '騰訊控股'},
            '00939': {'yahoo': '0939.HK', 'tradingview': 'HKEX:0939', 'name': '建設銀行'},
            '00941': {'yahoo': '0941.HK', 'tradingview': 'HKEX:0941', 'name': '中國移動'},
            '01211': {'yahoo': '1211.HK', 'tradingview': 'HKEX:1211', 'name': '比亞迪股份'},
            '01810': {'yahoo': '1810.HK', 'tradingview': 'HKEX:1810', 'name': '小米集團'},
            '02318': {'yahoo': '2318.HK', 'tradingview': 'HKEX:2318', 'name': '中國平安'},
            '03690': {'yahoo': '3690.HK', 'tradingview': 'HKEX:3690', 'name': '美團'},
            '09618': {'yahoo': '9618.HK', 'tradingview': 'HKEX:9618', 'name': '京東集團'},
            '09988': {'yahoo': '9988.HK', 'tradingview': 'HKEX:9988', 'name': '阿里巴巴'},
            # 新增股票
            '00008': {'yahoo': '0008.HK', 'tradingview': 'HKEX:0008', 'name': '銀河娛樂'},
            '01818': {'yahoo': '1818.HK', 'tradingview': 'HKEX:1818', 'name': '招金矿业'},
            '06823': {'yahoo': '6823.HK', 'tradingview': 'HKEX:6823', 'name': '香港電訊-SS'},
            '02715': {'yahoo': '2715.HK', 'tradingview': 'HKEX:2715', 'name': '埃斯顿'},
            '03416': {'yahoo': '3416.HK', 'tradingview': 'HKEX:3416', 'name': 'GlobalX國指兌證'},
            '06821': {'yahoo': '6821.HK', 'tradingview': 'HKEX:6821', 'name': '凱萊英'},
            '02675': {'yahoo': '2675.HK', 'tradingview': 'HKEX:2675', 'name': '精鋒醫療-B'},
            '01798': {'yahoo': '1798.HK', 'tradingview': 'HKEX:1798', 'name': '大唐新能源'},
        }

        if os.path.exists(self.mapping_path):
            try:
                with open(self.mapping_path, 'r', encoding='utf-8') as f:
                    user_mapping = json.load(f)
                    default_mapping.update(user_mapping)
            except Exception:
                pass

        return default_mapping

    def normalize_code(self, code: str) -> str:
        """
        标准化股票代码
        Args:
            code: 输入代码，如 '00005.HK', '5.HK', '00005', '5'
        Returns:
            标准化代码，如 '00005'
        """
        # 去掉 .HK 后缀
        code = code.replace('.HK', '').replace('.hk', '')

        # 转大写
        code = code.upper()

        # 补零到5位
        code = code.zfill(5)

        return code

    def to_yahoo(self, code: str) -> str:
        """
        转换为 Yahoo Finance 格式
        Args:
            code: 港股代码，如 '00005.HK'
        Returns:
            Yahoo Finance 格式，如 '0005.HK'
        """
        normalized = self.normalize_code(code)

        # 如果有预设映射，使用映射
        if normalized in self.mapping:
            return self.mapping[normalized]['yahoo']

        # 否则自动转换 (去掉前导零)
        return normalized.lstrip('0') + '.HK'

    def to_tradingview(self, code: str) -> str:
        """
        转换为 TradingView 格式
        Args:
            code: 港股代码，如 '00005.HK'
        Returns:
            TradingView 格式，如 'HKEX:0005'
        """
        normalized = self.normalize_code(code)

        # 如果有预设映射，使用映射
        if normalized in self.mapping:
            return self.mapping[normalized]['tradingview']

        # 否则自动转换
        return 'HKEX:' + normalized.lstrip('0')

    def to_full_hk(self, code: str) -> str:
        """
        转换为完整港股代码格式
        Args:
            code: 港股代码
        Returns:
            完整格式，如 '00005.HK'
        """
        normalized = self.normalize_code(code)
        return normalized + '.HK'

    def get_name(self, code: str) -> str:
        """
        获取股票名称
        Args:
            code: 港股代码
        Returns:
            股票名称
        """
        normalized = self.normalize_code(code)
        if normalized in self.mapping:
            return self.mapping[normalized]['name']
        return f'Unknown ({normalized})'

    def convert_all(self, code: str) -> dict:
        """
        获取所有格式的转换结果
        Args:
            code: 港股代码
        Returns:
            包含所有格式的字典
        """
        normalized = self.normalize_code(code)
        return {
            'original': code,
            'normalized': normalized,
            'full_hk': self.to_full_hk(code),
            'yahoo': self.to_yahoo(code),
            'tradingview': self.to_tradingview(code),
            'name': self.get_name(code)
        }


# 测试
if __name__ == '__main__':
    converter = HKTickerConverter()

    test_codes = [
        '00005.HK',
        '00700.HK',
        '00008.HK',
        '06823.HK',
        '5.HK',
        '5',
    ]

    print("=== 港股代码转换测试 ===\n")
    for code in test_codes:
        result = converter.convert_all(code)
        print(f"输入: {code}")
        print(f"  标准化: {result['normalized']}")
        print(f"  完整HK: {result['full_hk']}")
        print(f"  Yahoo: {result['yahoo']}")
        print(f"  TradingView: {result['tradingview']}")
        print(f"  名称: {result['name']}")
        print()
