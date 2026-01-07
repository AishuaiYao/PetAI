import time
import ujson as json
import urequests as requests
import ubinascii
from machine import I2S, Pin
import network
import socket
import gc

# --- 配置 ---
WIFI_SSID = "CMCC-huahua"
WIFI_PASSWORD = "*HUAHUAshi1zhimao"
API_KEY = 'sk-943f95da67d04893b70c02be400e2935'
MODEL_NAME = "qwen3-asr-flash"
API_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"

SAMPLE_RATE = 16000
COLLECT_SECONDS = 5  # 采集2秒

# 引脚
mic = I2S(0, sck=Pin(12), ws=Pin(13), sd=Pin(14),
          mode=I2S.RX, bits=32, format=I2S.MONO,
          rate=SAMPLE_RATE, ibuf=40000)


# --- 网络状态检查函数 ---
def check_network_status():
    """检查网络状态，包括AP模式"""
    print("=== 网络状态检查 ===")

    # 检查AP模式
    ap = network.WLAN(network.AP_IF)
    ap_active = ap.active()
    print(f"AP模式状态: {'开启' if ap_active else '关闭'}")
    if ap_active:
        print("⚠️ 警告: AP模式已开启，正在关闭以节省资源")
        ap.active(False)
        print("已关闭AP模式")

    # 检查STA模式
    sta = network.WLAN(network.STA_IF)
    sta_active = sta.active()
    print(f"STA模式状态: {'开启' if sta_active else '关闭'}")

    if sta.isconnected():
        print("WiFi连接状态: 已连接")
        config = sta.ifconfig()
        print(f"IP地址: {config[0]}")
    else:
        print("WiFi连接状态: 未连接")

    print("=== 网络检查结束 ===\n")
    return sta.isconnected()


# --- 核心函数 ---
def connect_wifi():
    print("开始连接Wi-Fi...")

    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    # 先检查是否已连接
    if wlan.isconnected():
        print(f"✅ 已连接Wi-Fi，IP: {wlan.ifconfig()[0]}")
        return True

    # 连接Wi-Fi
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)
    print(f"正在连接到 {WIFI_SSID}...")

    for i in range(30):  # 30次尝试
        if wlan.isconnected():
            print("✅ Wi-Fi连接成功")
            print(f"IP地址: {wlan.ifconfig()[0]}")
            return True

        if i % 5 == 0:  # 每5次打印一次状态
            print(f"连接状态: 尝试 {i + 1}/30")
        time.sleep(0.5)

    print("❌ Wi-Fi连接失败")
    return False


def collect_audio():
    """采集音频"""
    print(f"🎤 开始采集{COLLECT_SECONDS}秒音频...")

    start_time = time.time()

    # 计算需要的数据量
    total_bytes = COLLECT_SECONDS * SAMPLE_RATE * 4
    chunk_size = 3200
    collected = bytearray()

    while len(collected) < total_bytes:
        chunk = bytearray(chunk_size)
        mic.readinto(chunk)
        collected.extend(chunk)

    end_time = time.time()
    print(f"✅ 采集完成: {len(collected)} 字节，耗时: {end_time - start_time:.2f}秒")
    return collected


def create_wav_441(audio_data):
    """为441模块音频创建WAV"""
    print("🎵 开始创建WAV文件...")

    start_time = time.time()

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
    print(f"✅ WAV文件创建完成，大小: {len(wav)} 字节，耗时: {end_time - start_time:.2f}秒")
    return wav


def call_api(wav_data):
    """调用API"""
    print("开始API调用...")
    total_start = time.time()

    # 1. Base64编码
    encode_start = time.time()
    audio_b64 = ubinascii.b2a_base64(wav_data)[:-1].decode('utf-8')
    encode_time = time.time() - encode_start
    print(f"Base64编码耗时: {encode_time:.3f}秒")

    # 2. 构建请求数据
    build_start = time.time()
    json_data = f'''{{
    "model": "{MODEL_NAME}",
    "input": {{
        "messages": [
            {{
                "role": "user",
                "content": [
                    {{
                        "audio": "data:audio/wav;base64,{audio_b64}"
                    }}
                ]
            }}
        ]
    }},
    "parameters": {{
        "result_format": "message",
        "language": "zh-CN"
    }}
}}'''

    headers = {
        'Authorization': f'Bearer {API_KEY}',
        'Content-Type': 'application/json'
    }
    build_time = time.time() - build_start
    print(f"请求构建耗时: {build_time:.3f}秒")

    # 3. 发送HTTP请求
    request_start = time.time()
    try:
        response = requests.post(API_URL, headers=headers, data=json_data, timeout=30)
        request_time = time.time() - request_start
        print(f"HTTP请求耗时: {request_time:.3f}秒")
        print(f"状态码: {response.status_code}")

        if response.status_code == 200:
            # 解析响应
            parse_start = time.time()
            result = response.json()
            text = result['output']['choices'][0]['message']['content'][0]['text']
            parse_time = time.time() - parse_start

            total_time = time.time() - total_start
            print(f"响应解析耗时: {parse_time:.3f}秒")
            print(f"API调用总耗时: {total_time:.3f}秒")
            print(f"识别结果: {text}")

            return text
        else:
            print(f"❌ API返回错误: {response.status_code}")
            return None

    except Exception as e:
        print(f"❌ HTTP请求失败: {e}")
        return None


# --- 主循环 ---
def main():
    print("====== 语音识别程序启动 ======")

    # 连接Wi-Fi
    if not connect_wifi():
        print("❌ Wi-Fi连接失败，程序退出")
        return

    # 检查网络状态
    check_network_status()

    # 内存状态
    gc.collect()
    free_mem = gc.mem_free()
    total_mem = gc.mem_alloc() + free_mem
    print(f"内存状态:")
    print(f"  总内存: {total_mem} 字节")
    print(f"  空闲内存: {free_mem} 字节")
    print(f"  使用率: {gc.mem_alloc() / total_mem * 100:.1f}%")

    print(f"\n开始定时采集，每{COLLECT_SECONDS}秒一次\n")

    cycle_count = 0

    while True:
        cycle_count += 1
        cycle_start_time = time.time()
        print(f"\n====== 第{cycle_count}轮循环开始 ======")

        try:
            # 1. 采集音频
            audio_start = time.time()
            raw_audio = collect_audio()
            audio_time = time.time() - audio_start

            # 2. 创建WAV
            wav_start = time.time()
            wav_data = create_wav_441(raw_audio)
            wav_time = time.time() - wav_start

            # 3. 调用API
            api_start = time.time()
            result = call_api(wav_data)
            api_time = time.time() - api_start

            # 4. 显示本轮统计
            cycle_total_time = time.time() - cycle_start_time
            print(f"\n====== 第{cycle_count}轮循环统计 ======")
            print(f"  音频采集: {audio_time:.2f}秒")
            print(f"  WAV创建: {wav_time:.2f}秒")
            print(f"  API调用: {api_time:.2f}秒")
            print(f"  循环总耗时: {cycle_total_time:.2f}秒")
            print("===============================\n")

            # 5. 定期检查和内存清理
            if cycle_count % 3 == 0:  # 每3轮检查一次网络
                gc.collect()
                check_network_status()

            print("等待下一轮...\n")

        except KeyboardInterrupt:
            print("\n====== 程序结束 ======")
            print(f"完成循环数: {cycle_count}")
            break
        except Exception as e:
            print(f"错误: {e}")
            time.sleep(1)


if __name__ == "__main__":
    main()

#
#
# >>> %Run -c $EDITOR_CONTENT
#
# MPY: soft reboot
# ====== 语音识别程序启动 ======
# 开始连接Wi-Fi...
# ✅ 已连接Wi-Fi，IP: 192.168.1.23
# === 网络状态检查 ===
# AP模式状态: 关闭
# STA模式状态: 开启
# WiFi连接状态: 已连接
# IP地址: 192.168.1.23
# === 网络检查结束 ===
#
# 内存状态:
#   总内存: 8321536 字节
#   空闲内存: 8311424 字节
#   使用率: 0.1%
#
# 开始定时采集，每5秒一次
#
#
# ====== 第1轮循环开始 ======
# 🎤 开始采集5秒音频...
# ✅ 采集完成: 320000 字节，耗时: 5.00秒
# 🎵 开始创建WAV文件...
# ✅ WAV文件创建完成，大小: 320044 字节，耗时: 0.00秒
# 开始API调用...
# Base64编码耗时: 0.000秒
# 请求构建耗时: 1.000秒
# HTTP请求耗时: 2.000秒
# 状态码: 200
# 响应解析耗时: 0.000秒
# API调用总耗时: 3.000秒
# 识别结果: 下官不是怕嘛？哎，那什么，您请坐呀，坐。
#
# ====== 第1轮循环统计 ======
#   音频采集: 5.00秒
#   WAV创建: 0.00秒
#   API调用: 3.00秒
#   循环总耗时: 8.00秒
# ===============================
#
# 等待下一轮...
#
#
# ====== 第2轮循环开始 ======
# 🎤 开始采集5秒音频...
# ✅ 采集完成: 320000 字节，耗时: 5.00秒
# 🎵 开始创建WAV文件...
# ✅ WAV文件创建完成，大小: 320044 字节，耗时: 0.00秒
# 开始API调用...
# Base64编码耗时: 0.000秒
# 请求构建耗时: 1.000秒
# HTTP请求耗时: 2.000秒
# 状态码: 200
# 响应解析耗时: 0.000秒
# API调用总耗时: 3.000秒
# 识别结果: 刑部大人，本官要的名单。
#
# ====== 第2轮循环统计 ======
#   音频采集: 5.00秒
#   WAV创建: 0.00秒
#   API调用: 3.00秒
#   循环总耗时: 8.00秒
# ===============================
#
# 等待下一轮...
#
#
# ====== 第3轮循环开始 ======
# 🎤 开始采集5秒音频...
#
# ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
#
# ====== 程序结束 ======
# 完成循环数: 3
#
# MPY: soft reboot
# MicroPython v1.26.0 on 2025-08-09; Generic ESP32S3 module with Octal-SPIRAM with ESP32S3
# Type "help()" for more information.
# >>>
