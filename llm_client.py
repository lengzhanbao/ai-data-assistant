"""
LLM 客户端：兼容 OpenAI Chat Completions 协议。
支持任意 OpenAI 兼容端点（如 opencode / glm / deepseek / 本地 ollama）。
配置方式（环境变量）：
  LLM_BASE_URL  - 如 https://api.openai.com/v1 或你的私有网关
  LLM_API_KEY   - API Key（没有可不填，部分免费网关不需要）
  LLM_MODEL     - 模型名，如 gpt-4o-mini / glm-4 / deepseek-chat
"""
import os
import json
import requests

BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
API_KEY = os.getenv("LLM_API_KEY", "")
MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")


def chat(system: str, user: str, temperature: float = 0.2, timeout: int = 60) -> str:
    """调用 LLM，返回纯文本回复。"""
    if not API_KEY and "openai.com" in BASE_URL:
        raise RuntimeError(
            "未配置 LLM_API_KEY。请在环境变量中设置 LLM_BASE_URL / LLM_API_KEY / LLM_MODEL，"
            "或用你已有的 opencode / glm 等兼容端点。"
        )
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
    }
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"

    resp = requests.post(
        f"{BASE_URL.rstrip('/')}/chat/completions",
        headers=headers,
        data=json.dumps(payload),
        timeout=timeout,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"LLM 调用失败 {resp.status_code}: {resp.text[:500]}")
    data = resp.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise RuntimeError(f"LLM 返回格式异常：{str(data)[:300]}")
    if not content or not str(content).strip():
        raise RuntimeError("LLM 返回空内容")
    return content


if __name__ == "__main__":
    # 自检：确认能连通
    print(chat("你是数据分析助手。", "只回复两个字：就绪"))
