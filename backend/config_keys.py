# StockAI API Key 配置文件
#
# 使用说明：
# 1. SiliconFlow API Key：
#    访问 https://cloud.siliconflow.cn/account/ak
#    注册账户并获取 API Key（格式: sk-xxx）
#
# 2. 填写下方的 API Key

SILICONFLOW_API_KEY = "sk-huycdqozhnqyjzaronoirorvmjsaftmvpyrvvdihkvdbwvvf"  # 硅基流动 API Key（已启用）
CLAUDE_API_KEY = ""  # 在这里填写你的 Claude API Key
DEEPSEEK_API_KEY = "sk-a28f20ce1dad414daf17ad88981e540b"  # DeepSeek API Key（已配置）
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"  # DeepSeek API 地址

# 硅基流动模型配置
# ⚠️ 2026-04-02 最新价格：
#   Qwen/Qwen2.5-7B-Instruct  = 完全免费（✅ 当前使用）
#   Qwen/Qwen3-8B            = 完全免费（备选，更强）
#   Qwen/Qwen2.5-72B-Instruct = ¥4.13/百万（❌ 禁用，太贵）
SILICONFLOW_MODELS = {
    'qwen': 'Qwen/Qwen2.5-7B-Instruct',        # ✅ 当前使用（完全免费）
    # 'qwen': 'Qwen/Qwen3-8B',                # 备选：更强但也是免费
    'glm': 'THUDM/GLM-4-9B-0414',             # GLM-4（免费备选）
    'deepseek_r1': 'deepseek-ai/DeepSeek-R1-Distill-Qwen-7B'  # 免费推理模型
}
