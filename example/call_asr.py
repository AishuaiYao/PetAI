# esp32_s3_asr_send_wav.py
import time
import ujson as json
import urequests as requests
import ubinascii
from machine import I2S, Pin
import network

# --- 1. 配置区域 ---
# Wi-Fi 配置
WIFI_SSID = "CMCC-huahua"
WIFI_PASSWORD = "*HUAHUAshi1zhimao"

# 阿里云通义千问API配置
API_KEY = 'sk-943f95da67d04893b70c02be400e2935'
MODEL_NAME = "qwen3-asr-flash"
API_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"

# I2S麦克风 (INMP441) 配置
SAMPLE_RATE = 16000
BITS_PER_SAMPLE = 16
CHANNELS = 1

# 根据您的连接修改引脚
SCK_PIN = Pin(42)
WS_PIN = Pin(41)
SD_PIN = Pin(40)

# VAD (语音活动检测) 配置
# !!! 注意：您设置的阈值非常高，可能需要根据新的打印信息进行调整 !!!
ENERGY_THRESHOLD_SPEECH = 1000000
ENERGY_THRESHOLD_SILENCE = 500000
MIN_SPEECH_DURATION = 0.3
SILENCE_DURATION = 0.8
FRAME_SIZE_BYTES = 1024
MAX_RECORD_DURATION = 10.0


# --- 2. 辅助函数 ---

def connect_wifi():
    """连接到Wi-Fi网络"""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print(f'正在连接到Wi-Fi: {WIFI_SSID}...')
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        while not wlan.isconnected():
            time.sleep(0.5)
            print('.', end='')
    print('\nWi-Fi连接成功！')
    print('网络配置:', wlan.ifconfig())


def calculate_energy_python(audio_data):
    """使用纯Python计算音频帧的能量"""
    if len(audio_data) == 0: return 0
    samples = [int.from_bytes(audio_data[i:i + 2], 'little', True) for i in range(0, len(audio_data), 2)]
    # 对能量值进行缩放，使其更易于观察和设置阈值
    # 原始能量可能非常大，除以一个常数（如1000）可以让阈值在几千到几万的范围
    return sum(s * s for s in samples) / len(samples) / 1000.0


def create_wav_header(sample_rate, bits_per_sample, num_channels, num_samples):
    """生成WAV文件头"""
    datasize = num_samples * num_channels * bits_per_sample // 8
    o = bytes("RIFF", 'ascii')
    o += (datasize + 36).to_bytes(4, 'little')
    o += bytes("WAVE", 'ascii')
    o += bytes("fmt ", 'ascii')
    o += (16).to_bytes(4, 'little')
    o += (1).to_bytes(2, 'little')
    o += (num_channels).to_bytes(2, 'little')
    o += (sample_rate).to_bytes(4, 'little')
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    o += (byte_rate).to_bytes(4, 'little')
    block_align = num_channels * bits_per_sample // 8
    o += (block_align).to_bytes(2, 'little')
    o += (bits_per_sample).to_bytes(2, 'little')
    o += bytes("data", 'ascii')
    o += (datasize).to_bytes(4, 'little')
    return o


def call_asr_api_with_wav(wav_data):
    """调用ASR API，发送一个完整的WAV文件。"""
    print("📡 正在调用API (发送完整WAV文件)...")

    try:
        # --- 打印信息 1: 音频时长 ---
        # 计算音频时长（秒）
        audio_duration = len(wav_data) / (SAMPLE_RATE * BITS_PER_SAMPLE / 8)
        print(f"   - 待识别音频时长: {audio_duration:.2f} 秒")
        print(f"   - 待识别音频大小: {len(wav_data)} 字节")

        # --- 打印信息 2: Base64编码耗时 ---
        start_b64 = time.time()
        audio_b64 = ubinascii.b2a_base64(wav_data)[:-1].decode('utf-8')
        duration_b64 = time.time() - start_b64
        print(f"   - Base64编码完成，耗时: {duration_b64:.2f}s")

        audio_url = f"data:audio/wav;base64,{audio_b64}"

        payload = {
            "model": MODEL_NAME,
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": [{"audio": audio_url}]
                    }
                ]
            },
            "parameters": {"result_format": "message"}
        }

        headers = {
            'Authorization': f'Bearer {API_KEY}',
            'Content-Type': 'application/json'
        }

        # --- 打印信息 3: 网络请求耗时 ---
        start_request = time.time()
        response = requests.post(API_URL, headers=headers, data=json.dumps(payload), timeout=30)
        duration_request = time.time() - start_request

        if response.status_code == 200:
            result = response.json()
            text = result['output']['choices'][0]['message']['content'][0]['text']
            print(f"\n✅ API响应成功")
            print(f"   - 网络请求耗时: {duration_request:.2f}s")
            print(f"   - 识别结果: {text}")
            return True
        else:
            print(f"\n❌ API错误: {response.status_code}")
            print(f"   - 网络请求耗时: {duration_request:.2f}s")
            print(f"   - 错误信息: {response.text}")
            return False

    except Exception as e:
        print(f"\n❌ API调用过程中发生异常: {e}")
        import sys
        sys.print_exception(e)
        return False


def real_time_asr_serial():
    """核心的串行语音识别循环"""
    print("正在初始化I2S麦克风...")
    i2s = I2S(0, sck=SCK_PIN, ws=WS_PIN, sd=SD_PIN, mode=I2S.RX, bits=BITS_PER_SAMPLE, format=I2S.MONO,
              rate=SAMPLE_RATE, ibuf=4096)

    frame_duration = FRAME_SIZE_BYTES / (SAMPLE_RATE * CHANNELS * BITS_PER_SAMPLE / 8)
    call_count = 0

    print("\n🎤 开始监听，等待语音... ")
    print("=" * 30)

    try:
        while True:
            pcm_buffer = bytearray()
            is_recording = False
            silence_frames = 0

            while True:
                audio_frame = bytearray(FRAME_SIZE_BYTES)
                num_bytes_read = i2s.readinto(audio_frame)

                if num_bytes_read > 0:
                    energy = calculate_energy_python(audio_frame[:num_bytes_read])

                    # --- 打印信息 4: 实时能量值 ---
                    # 为了避免刷屏太快，我们只在录音状态或能量变化明显时打印
                    if is_recording or energy > ENERGY_THRESHOLD_SPEECH / 2:
                        print(f"   [VAD] 能量: {energy:.2f} | 状态: {'录音中' if is_recording else '等待中'}")

                    if not is_recording:
                        if energy > ENERGY_THRESHOLD_SPEECH:
                            is_recording = True
                            print(f"\n🔊 检测到语音开始...")
                            pcm_buffer.extend(audio_frame[:num_bytes_read])
                    else:
                        pcm_buffer.extend(audio_frame[:num_bytes_read])

                        if len(pcm_buffer) > SAMPLE_RATE * (BITS_PER_SAMPLE // 8) * MAX_RECORD_DURATION:
                            print(f"\n⚠️  录音超时，强制结束。")
                            break

                        if energy < ENERGY_THRESHOLD_SILENCE:
                            silence_frames += 1
                            if silence_frames * frame_duration > SILENCE_DURATION:
                                print(f"\n🔇 检测到语音结束。")
                                break
                        else:
                            silence_frames = 0

            if len(pcm_buffer) > 0:
                call_count += 1
                print(f"\n📊 第 {call_count} 次识别:")

                num_samples = len(pcm_buffer) // (BITS_PER_SAMPLE // 8)
                wav_header = create_wav_header(SAMPLE_RATE, BITS_PER_SAMPLE, CHANNELS, num_samples)
                wav_data = wav_header + pcm_buffer

                # --- 打印信息 5: 总API调用耗时 ---
                start_api_total = time.time()
                call_asr_api_with_wav(wav_data)
                duration_api_total = time.time() - start_api_total
                print(f"   - 本次API调用总耗时: {duration_api_total:.2f}s")

                print("-" * 30)
                print("🎤 等待下一段语音...")
            else:
                print("🎤 等待下一段语音...")

    except KeyboardInterrupt:
        print("\n\n" + "=" * 30)
        print("🛑 用户中断，程序停止。")
    except Exception as e:
        print(f"\n\n🛑 程序发生严重错误: {e}")
        import sys
        sys.print_exception(e)
    finally:
        i2s.deinit()
        print("I2S已关闭。")


# --- 主程序入口 ---
if __name__ == "__main__":
    connect_wifi()
    real_time_asr_serial()
