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
TEXT = "你好作者你好啊，现在是tts测试"
VOICE = "Cherry"
LANGUAGE = "Chinese"
RECV_BUFFER_SIZE = 65536

# 调试配置
DEBUG_SAVE_SSE = True  # 是否保存SSE数据到文件
SSE_SAVE_COUNT = 0  # 计数器

# TTS API配置
API_HOST = "dashscope.aliyuncs.com"
API_PORT = 443
API_PATH = "/api/v1/services/aigc/multimodal-generation/generation"

# I2S音频硬件配置（参考test_speaker.py）
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
        ibuf=24000  # 优化缓冲区大小（16位数据建议采样率/2）
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


def extract_base64(stream_data, flag):
    start = '"data":"'
    end = '"'
    base64 = ''
    while start in stream_data:
        if flag == 0:
            ans = stream_data.find(start)
            if ans != -1:
                start_idx = ans + len(start)
                stream_data = stream_data[start_idx:]
                flag = 1
            else:
                return base64

        if flag == 1:
            ans = stream_data.find(end)
            if ans != -1:
                end_idx = ans
                base64, stream_data = base64 + stream_data[:end_idx], stream_data[end_idx:]
                flag = 0
            else:
                base64 += stream_data

    return base64, flag


def test_speaker(i2s):
    buf_size = 4096
    buf = bytearray(buf_size)

    with open("tts_raw.pcm", "rb") as f:
        while True:
            # 读取数据（确保每次读取完整的样本数）
            num_read = f.readinto(buf)
            # 关键2：处理最后一段不完整的数据（必须是2字节的倍数）
            if num_read == 0:
                break  # 播放完毕

            written = 0
            while written < num_read:
                written += i2s.write(buf[written:num_read])


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
    # test_speaker(i2s)

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

    flag = 0
    cnt = 0
    while True:
        cnt += 1
        chunk = sock.read(RECV_BUFFER_SIZE)

        if not chunk:
            break
        row_data = chunk.decode('utf-8').replace("\n", '')
        if cnt == 1:
            print(row_data)

        base64, flag = extract_base64(row_data, flag)

        if flag:
            audio_bytes = ubinascii.a2b_base64(base64)

            i2s.write(audio_bytes)


# ===================== 主程序 =====================
def main():
    """主程序入口"""
    print("\n" + "=" * 50)
    print("ESP32 TTS 流式播放程序")
    print("=" * 50)

    tts_api_request(TEXT)


if __name__ == "__main__":
    main()






