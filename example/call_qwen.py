import network
import urequests
import time

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

# --- 3. 构建并发送 POST 请求 (保证成功的核心) ---
question = "who are you"
escaped_q = question.replace('"', '\\"')

# 【核心】使用 f-string 直接构建最终的 JSON 字符串
payload_str = f'{{"model":"qwen-plus","messages":[{{"role":"system","content":"You are a helpful assistant."}},{{"role":"user","content":"{escaped_q}"}}]}}'

try:
    print("\n--- 发送的 JSON 字符串 ---")
    print(payload_str)
    print("--------------------------")
    
    # 发送请求，将构建好的字符串传递给 data 参数
    response = urequests.post(URL, headers=HEADERS, data=payload_str)
    
    if response.status_code == 200:
        print("\n--- 大模型回复 ---")
        print(response.json()['choices'][0]['message']['content'])
        print("-------------------")
    else:
        print(f"\n请求失败，状态码: {response.status_code}")
        print("响应内容:", response.text)
        
finally:
    if 'response' in locals(): response.close()

print("\n程序结束。")