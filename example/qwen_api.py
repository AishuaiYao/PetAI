import requests
import json

# 1. 配置请求参数
api_key = "sk-943f95da67d04893b70c02be400e2935"
url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
headers = {"Authorization": f"Bearer {api_key}"}
payload = {
    "model": "qwen-plus",
    "messages": [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "你是谁？"},
    ]
}

# 2. 发送 POST 请求并获取响应
response = requests.post(url, headers=headers, json=payload)

# 3. 打印格式化后的完整 JSON 响应
print(json.dumps(response.json(), indent=2, ensure_ascii=False))