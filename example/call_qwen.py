import network
import urequests
import time
import json  # 【新增】导入 json 模块

# --- 1. 配置请求参数 ---
WIFI_SSID = "CMCC-huahua"
WIFI_PWD = "*HUAHUAshi1zhimao"
API_KEY = "sk-943f95da67d04893b70c02be400e2935"
URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
HEADERS = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

# --- 2. 连接 Wi-Fi ---
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
if not wlan.isconnected():
    print(f"连接 Wi-Fi: {WIFI_SSID}...")
    wlan.connect(WIFI_SSID, WIFI_PWD)
    while not wlan.isconnected(): time.sleep(0.5)
print("Wi-Fi 连接成功:", wlan.ifconfig())

# --- 3. 构建并发送 POST 请求 (修正版) ---
question = "写一首关于月亮的中文诗"  # 使用中文问题

# 【核心修改】
# 1. 首先，创建一个标准的 Python 字典对象
payload_dict = {
    "model": "qwen-plus",
    "messages": [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": question}
    ]
}

try:
    print("\n--- 待发送的 Python 字典 ---")
    print(payload_dict)
    print("--------------------------")

    # 2. 将字典编码为 JSON 格式的字符串，再转为 UTF-8 字节流
    # 这是解决中文问题的关键步骤
    payload_bytes = json.dumps(payload_dict).encode('utf-8')

    print("\n--- 实际发送的字节流 (UTF-8) ---")
    print(payload_bytes)
    print("---------------------------------")

    # 3. 发送请求，将编码后的字节流传递给 data 参数
    response = urequests.post(URL, headers=HEADERS, data=payload_bytes)

    if response.status_code == 200:
        print("\n--- 大模型回复 ---")
        # response.json() 会自动处理返回的 JSON 数据
        content = response.json()['choices'][0]['message']['content']
        print(content)
        print("-------------------")
    else:
        print(f"\n请求失败，状态码: {response.status_code}")
        print("响应内容:", response.text)

finally:
    if 'response' in locals():
        response.close()

print("\n程序结束。")