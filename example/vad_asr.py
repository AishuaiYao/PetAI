# esp32_s3_asr_send_wav.py
import time
import ujson as json
import urequests as requests
import ubinascii  # 确保导入的是 ubinascii
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
ENERGY_THRESHOLD_SPEECH = 1000
ENERGY_THRESHOLD_SILENCE = 100
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
    return sum(s * s for s in samples) / len(samples)


def create_wav_header(sample_rate, bits_per_sample, num_channels, num_samples):
    """生成WAV文件头"""
    datasize = num_samples * num_channels * bits_per_sample // 8
    o = bytes("RIFF", 'ascii')  # ChunkID
    o += (datasize + 36).to_bytes(4, 'little')  # ChunkSize
    o += bytes("WAVE", 'ascii')  # Format
    o += bytes("fmt ", 'ascii')  # Subchunk1ID
    o += (16).to_bytes(4, 'little')  # Subchunk1Size (16 for PCM)
    o += (1).to_bytes(2, 'little')  # AudioFormat (1 for PCM)
    o += (num_channels).to_bytes(2, 'little')  # NumChannels
    o += (sample_rate).to_bytes(4, 'little')  # SampleRate
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    o += (byte_rate).to_bytes(4, 'little')  # ByteRate
    block_align = num_channels * bits_per_sample // 8
    o += (block_align).to_bytes(2, 'little')  # BlockAlign
    o += (bits_per_sample).to_bytes(2, 'little')  # BitsPerSample
    o += bytes("data", 'ascii')  # Subchunk2ID
    o += (datasize).to_bytes(4, 'little')  # Subchunk2Size
    return o


def call_asr_api_with_wav(wav_data):
    """调用ASR API，发送一个完整的WAV文件。"""
    print("📡 正在调用API (发送完整WAV文件)...")

    try:
        # --- 错误修复 ---
        # 使用 ubinascii.b2a_base64 并去掉结尾的换行符
        audio_b64 = ubinascii.b2a_base64(wav_data)[:-1].decode('utf-8')

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

        start_time = time.time()
        response = requests.post(API_URL, headers=headers, data=json.dumps(payload), timeout=30)
        api_duration = time.time() - start_time

        if response.status_code == 200:
            result = response.json()
            text = result['output']['choices'][0]['message']['content'][0]['text']
            print(f"\n✅ API响应成功 (耗时: {api_duration:.2f}s)")
            print(f"└── 识别结果: {text}")
            return True
        else:
            print(f"\n❌ API错误: {response.status_code}")
            print(f"└── 错误信息: {response.text}")
            return False

    except Exception as e:
        print(f"\n❌ API调用过程中发生异常: {e}")
        import sys
        sys.print_exception(e)
        return False


def real_time_asr_serial():
    """核心的串行语音识别循环 (已修复I2S兼容性问题)"""
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

                call_asr_api_with_wav(wav_data)

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
