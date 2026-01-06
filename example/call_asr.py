import time
import ujson as json
import urequests as requests
import ubinascii
from machine import I2S, Pin
import network

# --- 配置 ---
WIFI_SSID = "CMCC-huahua"
WIFI_PASSWORD = "*HUAHUAshi1zhimao"
API_KEY = 'sk-943f95da67d04893b70c02be400e2935'
MODEL_NAME = "qwen3-asr-flash"
API_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"

SAMPLE_RATE = 16000
COLLECT_SECONDS = 5  # 采集5秒

# 引脚
mic = I2S(0, sck=Pin(12), ws=Pin(13), sd=Pin(14),
          mode=I2S.RX, bits=32, format=I2S.MONO,
          rate=SAMPLE_RATE, ibuf=40000)


# --- 核心函数 ---
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)
    for _ in range(20):
        if wlan.isconnected():
            print('✅ Wi-Fi已连接')
            return True
        time.sleep(0.5)
    return False


def collect_5s_audio():
    """采集5秒音频（441模块格式）"""
    print(f"🎤 开始采集{COLLECT_SECONDS}秒音频...")

    # 计算需要的数据量：5秒 × 16000样本/秒 × 4字节/样本
    total_bytes = COLLECT_SECONDS * SAMPLE_RATE * 4
    chunk_size = 3200  # 每次读0.05秒数据
    collected = bytearray()

    start_time = time.time()
    while len(collected) < total_bytes:
        chunk = bytearray(chunk_size)
        mic.readinto(chunk)
        collected.extend(chunk)

        # 显示进度
        progress = len(collected) / total_bytes * 100
        if time.time() - start_time >= 1:
            print(f"  进度: {progress:.0f}%")
            start_time = time.time()

    print(f"✅ 采集完成: {len(collected)} 字节")
    return collected


def create_wav_441(audio_data):
    """为441模块音频创建WAV"""
    # WAV头 (32位, 16000Hz, 单声道)
    datasize = len(audio_data)
    header = (
            b"RIFF" + (datasize + 36).to_bytes(4, 'little') + b"WAVE" +
            b"fmt " + b"\x10\x00\x00\x00" + b"\x01\x00" +  # PCM格式
            b"\x01\x00" +  # 单声道
            b"\x80\x3e\x00\x00" +  # 16000Hz
            b"\x00\xFA\x00\x00" +  # 字节率 = 16000*4 = 64000
            b"\x04\x00" +  # 块对齐 = 4字节
            b"\x20\x00" +  # 32位
            b"data" + datasize.to_bytes(4, 'little')
    )

    wav = bytearray()
    wav.extend(header)
    wav.extend(audio_data)
    return wav


def call_api(wav_data):
    """调用API"""
    print("📡 调用API...")

    # Base64编码
    audio_b64 = ubinascii.b2a_base64(wav_data)[:-1].decode('utf-8')

    # 构造请求
    payload = {
        "model": MODEL_NAME,
        "input": {
            "messages": [
                {"role": "user", "content": [{"audio": f"data:audio/wav;base64,{audio_b64}"}]}
            ]
        },
        "parameters": {"result_format": "message", "language": "zh-CN"}
    }

    headers = {
        'Authorization': f'Bearer {API_KEY}',
        'Content-Type': 'application/json'
    }

    try:
        response = requests.post(API_URL, headers=headers, data=json.dumps(payload), timeout=30)
        if response.status_code == 200:
            result = response.json()
            text = result['output']['choices'][0]['message']['content'][0]['text']
            print(f"✅ 识别结果: {text}")
            return text
        else:
            print(f"❌ API错误: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ 调用失败: {e}")
        return None


# --- 主循环 ---
def main():
    # 连接Wi-Fi
    if not connect_wifi():
        return

    print(f"\n开始定时采集，每{COLLECT_SECONDS}秒一次\n")

    while True:
        try:
            # 1. 采集5秒音频
            raw_audio = collect_5s_audio()

            # 2. 创建WAV
            wav_data = create_wav_441(raw_audio)

            # 3. 调用API
            result = call_api(wav_data)

            # 4. 等待下一轮（如果需要即时重复，去掉这行）
            print(f"\n等待下一轮...\n")

        except KeyboardInterrupt:
            print("\n程序结束")
            break
        except Exception as e:
            print(f"错误: {e}")
            time.sleep(1)


if __name__ == "__main__":
    main()
