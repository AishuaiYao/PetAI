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
COLLECT_SECONDS = 2  # 采集5秒

# 引脚
mic = I2S(0, sck=Pin(12), ws=Pin(13), sd=Pin(14),
          mode=I2S.RX, bits=32, format=I2S.MONO,
          rate=SAMPLE_RATE, ibuf=40000)


# --- 核心函数 ---
def connect_wifi():
    start_time = time.time()
    print(f"[{start_time:.3f}] 开始连接Wi-Fi...")

    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)

    for i in range(20):
        if wlan.isconnected():
            end_time = time.time()
            print(f"[{end_time:.3f}] ✅ Wi-Fi已连接，耗时: {end_time - start_time:.2f}秒")
            return True
        time.sleep(0.5)

    end_time = time.time()
    print(f"[{end_time:.3f}] ❌ Wi-Fi连接失败，耗时: {end_time - start_time:.2f}秒")
    return False


def collect_5s_audio():
    """采集5秒音频（441模块格式）"""
    start_time = time.time()
    print(f"[{start_time:.3f}] 🎤 开始采集{COLLECT_SECONDS}秒音频...")

    # 计算需要的数据量：5秒 × 16000样本/秒 × 4字节/样本
    total_bytes = COLLECT_SECONDS * SAMPLE_RATE * 4
    chunk_size = 3200  # 每次读0.05秒数据
    collected = bytearray()

    progress_start = time.time()
    while len(collected) < total_bytes:
        chunk = bytearray(chunk_size)
        chunk_start = time.time()
        mic.readinto(chunk)
        collected.extend(chunk)

        # 显示进度
        progress = len(collected) / total_bytes * 100
        if time.time() - progress_start >= 1:
            current_time = time.time()
            print(f"[{current_time:.3f}]   进度: {progress:.0f}%")
            progress_start = time.time()

    end_time = time.time()
    print(f"[{end_time:.3f}] ✅ 采集完成: {len(collected)} 字节，耗时: {end_time - start_time:.2f}秒")
    return collected


def create_wav_441(audio_data):
    """为441模块音频创建WAV"""
    start_time = time.time()
    print(f"[{start_time:.3f}] 🎵 开始创建WAV文件...")

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

    end_time = time.time()
    print(f"[{end_time:.3f}] ✅ WAV文件创建完成，大小: {len(wav)} 字节，耗时: {end_time - start_time:.2f}秒")
    return wav


def call_api(wav_data):
    """调用API"""
    start_time = time.time()
    print(f"[{start_time:.3f}] 📡 开始调用API...")

    # Base64编码
    encode_start = time.time()
    audio_b64 = ubinascii.b2a_base64(wav_data)[:-1].decode('utf-8')
    encode_end = time.time()
    print(f"[{encode_end:.3f}]   Base64编码完成，耗时: {encode_end - encode_start:.2f}秒")

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
        request_start = time.time()
        print(f"[{request_start:.3f}]   发送HTTP请求...")

        response = requests.post(API_URL, headers=headers, data=json.dumps(payload), timeout=30)
        request_end = time.time()
        print(
            f"[{request_end:.3f}]   HTTP响应接收完成，状态码: {response.status_code}，耗时: {request_end - request_start:.2f}秒")

        if response.status_code == 200:
            parse_start = time.time()
            result = response.json()
            text = result['output']['choices'][0]['message']['content'][0]['text']
            parse_end = time.time()

            end_time = time.time()
            total_time = end_time - start_time
            print(f"[{end_time:.3f}] ✅ API调用成功")
            print(f"[{end_time:.3f}]   解析结果耗时: {parse_end - parse_start:.2f}秒")
            print(f"[{end_time:.3f}]   总API耗时: {total_time:.2f}秒")
            print(f"[{end_time:.3f}]   识别结果: {text}")
            return text
        else:
            end_time = time.time()
            print(f"[{end_time:.3f}] ❌ API错误: {response.status_code}，总耗时: {end_time - start_time:.2f}秒")
            return None
    except Exception as e:
        end_time = time.time()
        print(f"[{end_time:.3f}] ❌ API调用失败: {e}，耗时: {end_time - start_time:.2f}秒")
        return None


# --- 主循环 ---
def main():
    total_start_time = time.time()
    print(f"[{total_start_time:.3f}] ====== 语音识别程序启动 ======")

    # 连接Wi-Fi
    if not connect_wifi():
        return

    print(f"\n[{time.time():.3f}] 开始定时采集，每{COLLECT_SECONDS}秒一次\n")

    cycle_count = 0

    while True:
        cycle_count += 1
        cycle_start_time = time.time()
        print(f"\n[{cycle_start_time:.3f}] ====== 第{cycle_count}轮循环开始 ======")

        try:
            # 1. 采集5秒音频
            audio_start = time.time()
            raw_audio = collect_5s_audio()
            audio_end = time.time()
            audio_time = audio_end - audio_start

            # 2. 创建WAV
            wav_start = time.time()
            wav_data = create_wav_441(raw_audio)
            wav_end = time.time()
            wav_time = wav_end - wav_start

            # 3. 调用API
            api_start = time.time()
            result = call_api(wav_data)
            api_end = time.time()
            api_time = api_end - api_start

            # 4. 显示本轮统计
            cycle_end_time = time.time()
            cycle_total_time = cycle_end_time - cycle_start_time

            print(f"\n[{cycle_end_time:.3f}] ====== 第{cycle_count}轮循环统计 ======")
            print(f"[{cycle_end_time:.3f}]   音频采集: {audio_time:.2f}秒")
            print(f"[{cycle_end_time:.3f}]   WAV创建: {wav_time:.2f}秒")
            print(f"[{cycle_end_time:.3f}]   API调用: {api_time:.2f}秒")
            print(f"[{cycle_end_time:.3f}]   循环总耗时: {cycle_total_time:.2f}秒")
            print(f"[{cycle_end_time:.3f}] ===============================\n")

            # 5. 等待下一轮（如果需要即时重复，去掉这行）
            print(f"[{time.time():.3f}] 等待下一轮...\n")

        except KeyboardInterrupt:
            total_end_time = time.time()
            print(f"\n[{total_end_time:.3f}] ====== 程序结束 ======")
            print(f"[{total_end_time:.3f}] 运行总时长: {total_end_time - total_start_time:.2f}秒")
            print(f"[{total_end_time:.3f}] 完成循环数: {cycle_count}")
            break
        except Exception as e:
            error_time = time.time()
            print(f"[{error_time:.3f}] 错误: {e}")
            time.sleep(1)


if __name__ == "__main__":
    main()
