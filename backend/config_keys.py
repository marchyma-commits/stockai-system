# StockAI API Key 配置文件 - Deployment Version
#
# Reads from environment variables first, falls back to defaults for local dev
#
# Deployment on Railway: set these in Railway Dashboard > Variables
import os

# ==================== DeepSeek API ====================
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "sk-dfc6b1209c354d56b017f1cf50ef6877")
DEEPSEEK_API_URL = os.environ.get("DEEPSEEK_API_URL", "https://api.deepseek.com/v1/chat/completions")

# ==================== SiliconFlow API ====================
SILICONFLOW_API_KEY = os.environ.get("SILICONFLOW_API_KEY", "sk-eqctxvzlxynzzlsjnczqmypfjclqxoanyzkzxdrunesdarqt")

# 硅基流动模型配置
SILICONFLOW_MODELS = {
    'qwen': os.environ.get("SILICONFLOW_MODEL_QWEN", "Qwen/Qwen2.5-7B-Instruct"),
    'glm': os.environ.get("SILICONFLOW_MODEL_GLM", "THUDM/GLM-4-9B-0414"),
    'deepseek_r1': os.environ.get("SILICONFLOW_MODEL_R1", "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B")
}

# ==================== Claude API (optional) ====================
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY", "")
