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

# VAD 参数（以 asr.py 为准）
SILENCE_THRESHOLD = 0.5  # 秒
MIN_SPEECH_DURATION = 0.3  # 秒
ENERGY_THRESHOLD_HIGH = 700  # 高能量阈值（语音开始）
ENERGY_THRESHOLD_LOW = 100  # 低能量阈值（语音结束）

# 音频处理参数
CHUNK_SIZE = 3200  # 与 asr.py 保持一致
BYTES_PER_SAMPLE = 2
FRAME_SIZE_BYTES = CHUNK_SIZE


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


def calculate_energy(audio_data):
    """计算音频能量（与 asr.py 逻辑一致）"""
    if len(audio_data) == 0:
        return 0

    # 将字节数据转换为16位整数
    samples = []
    for i in range(0, len(audio_data), 2):
        sample = int.from_bytes(audio_data[i:i + 2], 'little', True)
        samples.append(sample)

    # 计算能量（与 numpy 版本逻辑一致）
    energy_sum = 0
    for sample in samples:
        energy_sum += sample * sample

    if len(samples) > 0:
        return energy_sum / len(samples)
    return 0


def print_energy_bar(energy, max_energy=5000, width=20):
    """打印简化的能量条（适配 MicroPython）"""
    level = min(int((energy / max_energy) * width), width)
    bar = '█' * level + '░' * (width - level)
    status = "🔊 SPEAKING" if energy > ENERGY_THRESHOLD_HIGH else "🔈 LISTENING"
    print(f"\r[{bar}] {energy:6.0f} {status}", end='')


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
    print("\n📡 正在调用API (发送完整WAV文件)...")

    try:
        # 计算音频时长（秒）
        audio_duration = len(wav_data) / (SAMPLE_RATE * BITS_PER_SAMPLE / 8)
        print(f"   - 音频时长: {audio_duration:.2f}秒")
        print(f"   - 音频大小: {len(wav_data)}字节")

        # Base64编码
        start_b64 = time.time()
        audio_b64 = ubinascii.b2a_base64(wav_data)[:-1].decode('utf-8')
        duration_b64 = time.time() - start_b64
        print(f"   - Base64编码耗时: {duration_b64:.2f}s")

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

        # 发送请求
        start_request = time.time()
        response = requests.post(API_URL, headers=headers, data=json.dumps(payload), timeout=30)
        duration_request = time.time() - start_request

        if response.status_code == 200:
            result = response.json()
            text = result['output']['choices'][0]['message']['content'][0]['text']
            print(f"\n✅ API响应成功")
            print(f"   - 网络请求耗时: {duration_request:.2f}s")
            print(f"   - 识别结果: {text}")
            return text, True
        else:
            print(f"\n❌ API错误: {response.status_code}")
            print(f"   - 网络请求耗时: {duration_request:.2f}s")
            print(f"   - 错误信息: {response.text}")
            return None, False

    except Exception as e:
        print(f"\n❌ API调用异常: {e}")
        import sys
        sys.print_exception(e)
        return None, False


def real_time_asr_serial():
    """核心的串行语音识别循环（使用 asr.py 的 VAD 逻辑）"""
    print("正在初始化I2S麦克风...")
    i2s = I2S(0, sck=SCK_PIN, ws=WS_PIN, sd=SD_PIN, mode=I2S.RX, bits=BITS_PER_SAMPLE, format=I2S.MONO,
              rate=SAMPLE_RATE, ibuf=4096)

    # 计算帧时长
    frame_duration = CHUNK_SIZE / (SAMPLE_RATE * BYTES_PER_SAMPLE)

    vad_state = "SILENT"
    speech_buffer = bytearray()
    silence_frames = 0
    speech_frames = 0
    call_count = 0
    last_text = ""

    print("\n🎤 开始录音，VAD模式... (Ctrl+C停止)")
    print("=" * 50)
    print("能量显示（实时更新）:")

    try:
        while True:
            # 读取音频数据
            audio_frame = bytearray(CHUNK_SIZE)
            num_bytes_read = i2s.readinto(audio_frame)

            if num_bytes_read > 0:
                # 计算能量
                energy = calculate_energy(audio_frame[:num_bytes_read])

                # 打印能量条
                print_energy_bar(energy)

                # VAD 状态机（与 asr.py 完全一致）
                if vad_state == "SILENT":
                    if energy > ENERGY_THRESHOLD_HIGH:
                        speech_frames += 1
                        if speech_frames * frame_duration >= MIN_SPEECH_DURATION:
                            vad_state = "SPEAKING"
                            print(f"\n\n🔊 检测到语音开始 (能量: {energy:.0f})")
                            speech_buffer.extend(audio_frame[:num_bytes_read])
                    else:
                        speech_frames = 0

                elif vad_state == "SPEAKING":
                    speech_buffer.extend(audio_frame[:num_bytes_read])

                    if energy < ENERGY_THRESHOLD_LOW:
                        silence_frames += 1
                        if silence_frames * frame_duration >= SILENCE_THRESHOLD:
                            vad_state = "SILENT"
                            silence_frames = 0
                            speech_frames = 0

                            if len(speech_buffer) > 0:
                                call_count += 1
                                audio_duration = len(speech_buffer) / (SAMPLE_RATE * BYTES_PER_SAMPLE)

                                print(f"\n\n📊 第{call_count}次调用")
                                print(f"语音段: {audio_duration:.2f}秒 ({len(speech_buffer)}字节)")

                                # 创建 WAV 文件
                                num_samples = len(speech_buffer) // (BITS_PER_SAMPLE // 8)
                                wav_header = create_wav_header(SAMPLE_RATE, BITS_PER_SAMPLE, CHANNELS, num_samples)
                                wav_data = wav_header + speech_buffer

                                # 调用 API
                                start_time = time.time()
                                text, success = call_asr_api_with_wav(wav_data)
                                api_duration = time.time() - start_time

                                print(f"API总耗时: {api_duration:.2f}秒")

                                if success and text:
                                    print(f"✅ 识别结果: {text}")
                                    last_text = text
                                else:
                                    print(f"❌ 识别失败")

                                print("-" * 50)
                                speech_buffer = bytearray()
                                print("\n继续监听...")
                    else:
                        silence_frames = 0

    except KeyboardInterrupt:
        print("\n\n" + "=" * 50)
        print("🛑 识别结束")
        print(f"总调用次数: {call_count}")
        if last_text:
            print(f"最后识别结果: {last_text}")
    except Exception as e:
        print(f"\n\n🛑 程序发生错误: {e}")
        import sys
        sys.print_exception(e)
    finally:
        i2s.deinit()
        print("I2S已关闭。")


# --- 主程序入口 ---
if __name__ == "__main__":
    connect_wifi()
    real_time_asr_serial()



# >>> %Run -c $EDITOR_CONTENT
#
# MPY: soft reboot
#
# Wi-Fi连接成功！
# 网络配置: ('192.168.1.17', '255.255.255.0', '192.168.1.1', '192.168.1.1')
# 正在初始化I2S麦克风...
#
# 🎤 开始录音，VAD模式... (Ctrl+C停止)
# ==================================================
# 能量显示（实时更新）:
# [████████████████████] 3068199000 🔊 SPEAKING
#
# 🔊 检测到语音开始 (能量: 3068199000)
# [░░░░░░░░░░░░░░░░░░░░]      0 🔈 LISTENINGING
#
# 📊 第1次调用
# 语音段: 7.50秒 (240000字节)
#
# 📡 正在调用API (发送完整WAV文件)...
#    - 音频时长: 7.50秒
#    - 音频大小: 240044字节
#    - Base64编码耗时: 0.00s
#
# ❌ API调用异常: list index out of range
# Traceback (most recent call last):
#   File "<stdin>", line 150, in call_asr_api_with_wav
# IndexError: list index out of range
# API总耗时: 11.00秒
# ❌ 识别失败
# --------------------------------------------------
#
# 继续监听...
# [████████████████████] 19156748 🔊 SPEAKINGGG
#
# 🔊 检测到语音开始 (能量: 19156748)
# [░░░░░░░░░░░░░░░░░░░░]      0 🔈 LISTENINGING
#
# 📊 第2次调用
# 语音段: 8.60秒 (275200字节)
#
# 📡 正在调用API (发送完整WAV文件)...
#    - 音频时长: 8.60秒
#    - 音频大小: 275244字节
#    - Base64编码耗时: 1.00s
#
# ❌ API调用异常: list index out of range
# Traceback (most recent call last):
#   File "<stdin>", line 150, in call_asr_api_with_wav
# IndexError: list index out of range
# API总耗时: 14.00秒
# ❌ 识别失败
# --------------------------------------------------
#
# 继续监听...
# [████████████████████] 2635723800 🔊 SPEAKING
#
# 🔊 检测到语音开始 (能量: 2635723800)
# [░░░░░░░░░░░░░░░░░░░░]      0 🔈 LISTENINGGGG
#
# 📊 第3次调用
# 语音段: 4.60秒 (147200字节)
#
# 📡 正在调用API (发送完整WAV文件)...
#    - 音频时长: 4.60秒
#    - 音频大小: 147244字节
#    - Base64编码耗时: 0.00s
#
# ✅ API响应成功
#    - 网络请求耗时: 4.00s
#    - 识别结果: 测试一下测试一下。
# API总耗时: 4.00秒
# ✅ 识别结果: 测试一下测试一下。
# --------------------------------------------------
#
# 继续监听...
# [████████████████████] 1814788400 🔊 SPEAKING
#
# 🔊 检测到语音开始 (能量: 1814788400)
# [░░░░░░░░░░░░░░░░░░░░]      0 🔈 LISTENINGNGG
#
# 📊 第4次调用
# 语音段: 1.30秒 (41600字节)
#
# 📡 正在调用API (发送完整WAV文件)...
#    - 音频时长: 1.30秒
#    - 音频大小: 41644字节
#    - Base64编码耗时: 0.00s
#
# ❌ API调用异常: list index out of range
# Traceback (most recent call last):
#   File "<stdin>", line 150, in call_asr_api_with_wav
# IndexError: list index out of range
# API总耗时: 2.00秒
# ❌ 识别失败
# --------------------------------------------------
#
# 继续监听...
# [████████████████████] 1823567200 🔊 SPEAKING
#
# 🔊 检测到语音开始 (能量: 1823567200)
# [░░░░░░░░░░░░░░░░░░░░]      0 🔈 LISTENINGING
#
# 📊 第5次调用
# 语音段: 2.10秒 (67200字节)
#
# 📡 正在调用API (发送完整WAV文件)...
#    - 音频时长: 2.10秒
#    - 音频大小: 67244字节
#    - Base64编码耗时: 0.00s
#
# ❌ API调用异常: list index out of range
# Traceback (most recent call last):
#   File "<stdin>", line 150, in call_asr_api_with_wav
# IndexError: list index out of range
# API总耗时: 1.00秒
# ❌ 识别失败
# --------------------------------------------------
#
# 继续监听...
# [████████████████████] 76065040 🔊 SPEAKINGNG
#
# 🔊 检测到语音开始 (能量: 76065040)
# [░░░░░░░░░░░░░░░░░░░░]      0 🔈 LISTENINGGNG
#
# 📊 第6次调用
# 语音段: 2.20秒 (70400字节)
#
# 📡 正在调用API (发送完整WAV文件)...
#    - 音频时长: 2.20秒
#    - 音频大小: 70444字节
#    - Base64编码耗时: 0.00s
#
# ✅ API响应成功
#    - 网络请求耗时: 11.00s
#    - 识别结果: 测试了测试。
# API总耗时: 11.00秒
# ✅ 识别结果: 测试了测试。
# --------------------------------------------------
#
# 继续监听...
# [████████████████████] 1487923000 🔊 SPEAKING
#
# 🔊 检测到语音开始 (能量: 1487923000)
# [░░░░░░░░░░░░░░░░░░░░]      0 🔈 LISTENINGGGG
#
# 📊 第7次调用
# 语音段: 3.90秒 (124800字节)
#
# 📡 正在调用API (发送完整WAV文件)...
#    - 音频时长: 3.90秒
#    - 音频大小: 124844字节
#    - Base64编码耗时: 0.00s
#
# ❌ API调用异常: list index out of range
# Traceback (most recent call last):
#   File "<stdin>", line 150, in call_asr_api_with_wav
# IndexError: list index out of range
# API总耗时: 4.00秒
# ❌ 识别失败
# --------------------------------------------------
#
# 继续监听...
# [████████████████████] 22672396 🔊 SPEAKINGNG
#
# 🔊 检测到语音开始 (能量: 22672396)
# [░░░░░░░░░░░░░░░░░░░░]      0 🔈 LISTENINGGNG
#
# 📊 第8次调用
# 语音段: 33.80秒 (1081600字节)
#
# 📡 正在调用API (发送完整WAV文件)...
#    - 音频时长: 33.80秒
#    - 音频大小: 1081644字节
#
# ❌ API调用异常: memory allocation failed, allocating 1442193 bytes
# Traceback (most recent call last):
#   File "<stdin>", line 119, in call_asr_api_with_wav
# MemoryError: memory allocation failed, allocating 1442193 bytes
# API总耗时: 0.00秒
# ❌ 识别失败
# --------------------------------------------------
#
# 继续监听...
# [████████████████████] 20696704 🔊 SPEAKINGNG
#
# 🔊 检测到语音开始 (能量: 20696704)
# [░░░░░░░░░░░░░░░░░░░░]      0 🔈 LISTENINGING
#
# 📊 第9次调用
# 语音段: 11.30秒 (361600字节)
#
# 📡 正在调用API (发送完整WAV文件)...
#    - 音频时长: 11.30秒
#    - 音频大小: 361644字节
#    - Base64编码耗时: 0.00s
#
# ✅ API响应成功
#    - 网络请求耗时: 22.00s
#    - 识别结果: 测试一下测试一下。
# API总耗时: 22.00秒
# ✅ 识别结果: 测试一下测试一下。
# --------------------------------------------------
#
# 继续监听...
# [░░░░░░░░░░░░░░░░░░░░]      0 🔈 LISTENING
# ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
#
#
# ==================================================
# 🛑 识别结束
# 总调用次数: 9
# 最后识别结果: 测试一下测试一下。
# I2S已关闭。
#
# MPY: soft reboot
# MicroPython v1.26.0 on 2025-08-09; Generic ESP32S3 module with Octal-SPIRAM with ESP32S3
# Type "help()" for more information.
# >>>
