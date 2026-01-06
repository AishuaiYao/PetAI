# esp32_s3_asr_send_wav.py
import time
import ujson as json
import urequests as requests
import ubinascii
from machine import I2S, Pin
import network
import array

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
I2S_BITS = 32  # INMP441固定输出32位帧
ACTUAL_BITS_PER_SAMPLE = 16  # 我们实际存储16位数据
CHANNELS = 1

# 根据您的连接修改引脚
SCK_PIN = Pin(42)
WS_PIN = Pin(41)
SD_PIN = Pin(40)

# VAD 参数（调整阈值）
SILENCE_THRESHOLD = 0.5  # 秒
MIN_SPEECH_DURATION = 0.3  # 秒
ENERGY_THRESHOLD_HIGH = 40000  # 降低阈值
ENERGY_THRESHOLD_LOW = 30000  # 降低阈值

# 音频处理参数
CHUNK_SIZE = 3200  # 与 asr.py 保持一致
BYTES_PER_SAMPLE = 2  # 16位 = 2字节
I2S_BYTES_PER_SAMPLE = 4  # 32位 = 4字节


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


def process_inmp441_data(raw_data):
    """
    处理INMP441的32位数据，提取有效的24位音频数据并转换为16位
    INMP441输出：32位帧，其中24位是有效音频数据（补码格式），8位补零
    数据格式：大端，MSB对齐
    """
    processed_data = bytearray()

    # 每4个字节（32位）处理一次
    for i in range(0, len(raw_data), 4):
        if i + 3 < len(raw_data):
            # INMP441输出是大端，32位帧：
            # 字节0: 最高有效位 (MSB) - 24位数据的最高8位
            # 字节1: 中间8位
            # 字节2: 最低有效位 (LSB) - 24位数据的最低8位
            # 字节3: 补零 (通常为0x00)

            # 读取24位有符号整数（补码）
            # 注意：24位数据存储在字节0-2，字节3是填充
            b0 = raw_data[i]  # MSB
            b1 = raw_data[i + 1]
            b2 = raw_data[i + 2]  # LSB

            # 将24位补码转换为32位有符号整数
            # 如果最高位是1（负数），需要符号扩展
            if b0 & 0x80:  # 检查最高位
                # 负数：符号扩展
                sample_24bit = (b0 << 16) | (b1 << 8) | b2
                # 符号扩展到32位
                if sample_24bit & 0x800000:  # 检查24位的最高位
                    sample_32bit = sample_24bit | 0xFF000000  # 扩展符号位
                else:
                    sample_32bit = sample_24bit
            else:
                # 正数
                sample_32bit = (b0 << 16) | (b1 << 8) | b2

            # 转换为有符号32位整数
            if sample_32bit & 0x80000000:
                sample_32bit = sample_32bit - 0x100000000

            # 将32位缩放到16位（右移8位，因为INMP441的24位数据对齐到32位的高24位）
            sample_16bit = sample_32bit >> 8

            # 限制在16位范围内
            if sample_16bit > 32767:
                sample_16bit = 32767
            elif sample_16bit < -32768:
                sample_16bit = -32768

            # 转换为16位小端字节（WAV格式通常是小端）
            sample_bytes = sample_16bit.to_bytes(2, 'little', True)
            processed_data.extend(sample_bytes)

    return processed_data


def calculate_energy(audio_data):
    """计算音频能量（处理16位数据）"""
    if len(audio_data) < 2:
        return 0

    energy_sum = 0
    sample_count = 0

    # 将字节数据转换为16位整数（小端，有符号）
    for i in range(0, len(audio_data), 2):
        if i + 1 < len(audio_data):
            # 读取16位有符号整数（小端）
            sample = int.from_bytes(audio_data[i:i + 2], 'little', True)

            # 计算平方（能量）
            energy_sum += sample * sample
            sample_count += 1

    if sample_count > 0:
        return energy_sum / sample_count
    return 0


def print_energy_bar(energy, max_energy=10000, width=20):
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
    o += (1).to_bytes(2, 'little')  # PCM格式
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
        audio_duration = len(wav_data) / (SAMPLE_RATE * BYTES_PER_SAMPLE)
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
    """核心的串行语音识别循环"""
    print("正在初始化I2S麦克风...")
    # 使用32位读取INMP441
    i2s = I2S(0, sck=SCK_PIN, ws=WS_PIN, sd=SD_PIN, mode=I2S.RX, bits=I2S_BITS, format=I2S.MONO,
              rate=SAMPLE_RATE, ibuf=4096)

    # 计算帧时长
    # 每次读取的原始数据大小（字节）
    raw_chunk_size = CHUNK_SIZE * 2  # CHUNK_SIZE是16位数据大小，32位需要2倍
    frame_duration = CHUNK_SIZE / (SAMPLE_RATE * BYTES_PER_SAMPLE)

    vad_state = "SILENT"
    speech_buffer = bytearray()
    silence_frames = 0
    speech_frames = 0
    call_count = 0
    last_text = ""

    print("\n🎤 开始录音，VAD模式... (Ctrl+C停止)")
    print(f"I2S配置: {I2S_BITS}位帧，提取有效的24位音频数据并转换为16位")
    print("=" * 50)
    print("能量显示（实时更新）:")

    try:
        while True:
            # 读取原始32位数据
            raw_frame = bytearray(raw_chunk_size)
            num_bytes_read = i2s.readinto(raw_frame)

            if num_bytes_read > 0:
                # 处理INMP441数据，转换为16位
                processed_frame = process_inmp441_data(raw_frame[:num_bytes_read])

                # 计算能量
                energy = calculate_energy(processed_frame)

                # 打印能量条
                print_energy_bar(energy)

                # VAD 状态机
                if vad_state == "SILENT":
                    if energy > ENERGY_THRESHOLD_HIGH:
                        speech_frames += 1
                        if speech_frames * frame_duration >= MIN_SPEECH_DURATION:
                            vad_state = "SPEAKING"
                            print(f"\n\n🔊 检测到语音开始 (能量: {energy:.0f})")
                            speech_buffer.extend(processed_frame)
                    else:
                        speech_frames = 0

                elif vad_state == "SPEAKING":
                    speech_buffer.extend(processed_frame)

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
                                num_samples = len(speech_buffer) // BYTES_PER_SAMPLE
                                wav_header = create_wav_header(SAMPLE_RATE, ACTUAL_BITS_PER_SAMPLE, CHANNELS,
                                                               num_samples)
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


# --- 测试函数 ---
def test_inmp441_data():
    """测试INMP441数据读取和处理"""
    print("测试INMP441数据读取...")

    i2s = I2S(0, sck=SCK_PIN, ws=WS_PIN, sd=SD_PIN, mode=I2S.RX, bits=I2S_BITS, format=I2S.MONO,
              rate=SAMPLE_RATE, ibuf=4096)

    print("读取10帧数据测试:")
    for i in range(10):
        raw_data = bytearray(128)  # 32个样本 * 4字节
        num_bytes = i2s.readinto(raw_data)

        if num_bytes > 0:
            processed = process_inmp441_data(raw_data[:num_bytes])
            energy = calculate_energy(processed)

            # 显示原始数据的前几个字节
            print(f"帧{i}: 原始[{raw_data[0]:02X} {raw_data[1]:02X} {raw_data[2]:02X} {raw_data[3]:02X}] "
                  f"-> 能量: {energy:.0f}")

        time.sleep_ms(100)

    i2s.deinit()


# --- 主程序入口 ---
if __name__ == "__main__":
    connect_wifi()

    # 可选：先运行测试
    # test_inmp441_data()

    real_time_asr_serial()
