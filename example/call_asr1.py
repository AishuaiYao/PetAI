import time, ujson, urequests, ubinascii, network
from machine import I2S, Pin

# 配置
WIFI_SSID = "CMCC-huahua"
WIFI_PASSWORD = "*HUAHUAshi1zhimao"
API_KEY = 'sk-943f95da67d04893b70c02be400e2935'
SAMPLE_RATE = 16000
COLLECT_SECONDS = 5

# Wi-Fi
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect(WIFI_SSID, WIFI_PASSWORD)
while not wlan.isconnected():
    time.sleep(0.5)
print('Wi-Fi OK')

# 麦克风
mic = I2S(0, sck=Pin(12), ws=Pin(13), sd=Pin(14),
          mode=I2S.RX, bits=32, format=I2S.MONO,
          rate=SAMPLE_RATE, ibuf=40000)

while True:
    # 1. 采集5秒
    start = time.time()
    total_bytes = COLLECT_SECONDS * SAMPLE_RATE * 4
    collected = bytearray()
    while len(collected) < total_bytes:
        chunk = bytearray(3200)
        mic.readinto(chunk)
        collected.extend(chunk)
    print(f"采集: {time.time() - start:.2f}s")

    # 2. 创建WAV
    wav = bytearray()
    wav.extend(b"RIFF" + (len(collected) + 36).to_bytes(4,
                                                        'little') + b"WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80\x3e\x00\x00\x00\xFA\x00\x00\x04\x00\x20\x00data" + len(
        collected).to_bytes(4, 'little'))
    wav.extend(collected)

    # 3. Base64编码
    start = time.time()
    audio_b64 = ubinascii.b2a_base64(wav)[:-1].decode('utf-8')
    print(f"编码: {time.time() - start:.2f}s")

    # 4. API调用（直接调用，不加额外处理）
    start = time.time()
    try:
        response = urequests.post(
            "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
            headers={
                'Authorization': f'Bearer {API_KEY}',
                'Content-Type': 'application/json'
            },
            data=ujson.dumps({
                "model": "qwen3-asr-flash",
                "input": {"messages": [{"role": "user", "content": [{"audio": f"data:audio/wav;base64,{audio_b64}"}]}]},
                "parameters": {"result_format": "message", "language": "zh-CN"}
            })
        )

        api_time = time.time() - start
        print(f"API: {api_time:.2f}s")

        if response.status_code == 200:
            result = response.json()
            text = result['output']['choices'][0]['message']['content'][0]['text']
            print(f"识别: {text}")
        else:
            print(f"API失败: {response.status_code}")

    except Exception as e:
        print(f"API错误: {e}")

    print("-" * 30)
