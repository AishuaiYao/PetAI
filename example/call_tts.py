import socket
import json
import struct
import time
import network
import ubinascii

from machine import I2S, Pin

# ===================== 核心配置 =====================
# --- 配置 ---
WIFI_SSID = "CMCC-huahua"
WIFI_PASSWORD = "*HUAHUAshi1zhimao"
API_KEY = 'sk-943f95da67d04893b70c02be400e2935'
TEXT = "我是电子花花，你听的到吗"
VOICE = "Cherry"
LANGUAGE = "Chinese"
RECV_BUFFER_SIZE = 8192

# 调试配置
DEBUG_SAVE_SSE = True  # 是否保存SSE数据到文件
SSE_SAVE_COUNT = 0  # 计数器

# TTS API配置
API_HOST = "dashscope.aliyuncs.com"
API_PORT = 443
API_PATH = "/api/v1/services/aigc/multimodal-generation/generation"

I2S_SCK_PIN = 9
I2S_WS_PIN = 10
I2S_SD_PIN = 8
AMP_ENABLE_PIN = 21
SAMPLE_RATE = 24000
BITS = 16
CHANNELS = 1




# ===================== I2S音频初始化 =====================
def init_audio():
    # 1. 硬件初始化（优化缓冲区+明确配置）
    Pin(21, Pin.OUT).value(1)  # 启用功放
    # 关键优化：ibuf大小设置为采样率的1/2（24000/2=12000），匹配16位数据特性
    i2s = I2S(
        0,
        sck=Pin(9),
        ws=Pin(10),
        sd=Pin(8),
        mode=I2S.TX,
        bits=16,  # 匹配PCM：16位
        format=I2S.MONO,  # 匹配PCM：单声道
        rate=24000,  # 匹配PCM：24000Hz采样率
        ibuf=10000  # 优化缓冲区大小（16位数据建议采样率/2）
    )
    return i2s


# ===================== WiFi连接 =====================
def connect_wifi():
    """连接WiFi网络（适配ESP32 Micropython）"""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if wlan.isconnected():
        print("[WiFi] 已连接WiFi，跳过重连")
        print(f"[WiFi] IP地址: {wlan.ifconfig()[0]}")
        return True

    print(f"[WiFi] 正在连接WiFi: {WIFI_SSID}")
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)

    # 等待连接（超时15秒）
    timeout = 15
    while timeout > 0:
        if wlan.isconnected():
            print(f"[WiFi] WiFi连接成功，IP: {wlan.ifconfig()[0]}")
            return True
        timeout -= 1
        time.sleep(1)
        print(f"[WiFi] WiFi连接中...剩余{timeout}秒")

    print("[WiFi] WiFi连接失败！")
    return False


def parse_sse_line(line_str):
    """解析SSE数据行"""
    if not line_str.startswith('data:'):
        return None

    json_str = line_str[5:]
    if json_str == '[DONE]':
        return {"type": "done"}

    try:
        return {"type": "data", "data": json.loads(json_str)}
    except:
        return None

def handle_chunk_data(chunk):
    """处理数据块，返回(audio_data, is_done)"""
    if "output" not in chunk:
        return None, False

    if chunk["output"].get("finish_reason") == "stop":
        return None, True

    audio_info = chunk["output"].get("audio", {})
    if "data" in audio_info:
        return audio_info["data"], False

    return None, False



# ===================== TTS API请求（带实时播放） =====================
def tts_api_request(text):
    """
    核心函数：请求TTS API并实时播放音频
    """
    # 1. WiFi连接检查
    if not connect_wifi():
        return False, 0, []

    # 2. 初始化音频
    i2s = init_audio()

    # 2. 建立SSL连接
    print(f"[API] 连接TTS API: {API_HOST}:{API_PORT}")
    addr_info = socket.getaddrinfo(API_HOST, API_PORT)[0]
    sock = socket.socket(addr_info[0], addr_info[1], addr_info[2])
    sock.setsockopt(1, 8, RECV_BUFFER_SIZE)  # 8KB

    sock.settimeout(15)
    sock.connect(addr_info[-1])

    import ssl
    sock = ssl.wrap_socket(sock, server_hostname=API_HOST)
    print("[API] SSL连接建立成功")

    # 3. 构建请求
    payload_dict = {
        "model": "qwen3-tts-flash",
        "input": {"text": text},
        "parameters": {
            "voice": VOICE,
            "language_type": LANGUAGE
        }
    }
    payload = json.dumps(payload_dict)

    # 4. 发送请求
    payload_bytes = payload.encode('utf-8')

    request_headers = (
        f"POST {API_PATH} HTTP/1.1\r\n"
        f"Host: {API_HOST}\r\n"
        f"Authorization: Bearer {API_KEY}\r\n"
        f"Content-Type: application/json\r\n"
        f"X-DashScope-SSE: enable\r\n"
        f"Content-Length: {len(payload_bytes)}\r\n"
        f"Connection: close\r\n\r\n"
    )

    sock.write(request_headers.encode('utf-8'))
    sock.write(payload_bytes)
    print(f"[API] TTS请求已发送，文本: {text}")

    count = 0
    buffer = ""

    while True:
        chunk = sock.read(RECV_BUFFER_SIZE)
        if not chunk:
            break

        buffer += chunk.decode('utf-8')

        while '\n' in buffer:
            line, buffer = buffer.split('\n', 1)
            line = line.strip()

            if not line:
                continue

            parsed = parse_sse_line(line)
            if parsed is None:
                continue

            count += 1

            if parsed["type"] == "done":
                break

            audio_data, is_done = handle_chunk_data(parsed["data"])
            if audio_data:
                audio_bytes = ubinascii.a2b_base64(audio_data)
                i2s.write(audio_bytes)
                print(f"✓ 播放块{count}, 大小: {len(audio_bytes)}")

            if is_done:
                break

    print(f"共获取 {count} 条数据")


# ===================== 主程序 =====================
def main():
    """主程序入口"""
    print("\n" + "=" * 50)
    print("ESP32 TTS 流式播放程序")
    print("=" * 50)

    tts_api_request(TEXT)


if __name__ == "__main__":
    main()






