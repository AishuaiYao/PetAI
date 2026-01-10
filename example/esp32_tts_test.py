import socket
import json
import struct
import time
import network
from machine import I2S, Pin

# ===================== 核心配置 =====================
# --- 配置 ---
WIFI_SSID = "CMCC-huahua"
WIFI_PASSWORD = "*HUAHUAshi1zhimao"
API_KEY = 'sk-943f95da67d04893b70c02be400e2935'
TEXT = "测试文本"
VOICE = "Cherry"
LANGUAGE = "Chinese"

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


# ===================== Base64解码 =====================
_b64chars = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"


def base64_decode(s):
    """轻量级base64解码（Micropython兼容）"""
    s = s.rstrip(b'=')
    res = bytearray()
    for i in range(0, len(s), 4):
        chunk = s[i:i + 4]
        while len(chunk) < 4:
            chunk += b'='
        idx = [_b64chars.find(c) for c in chunk]
        b = (idx[0] << 18) | (idx[1] << 12) | (idx[2] << 6) | idx[3]
        res.extend(struct.pack('!I', b)[1:])
    pad = len(s) % 4
    if pad:
        del res[-pad:]
    return bytes(res)


# ===================== I2S音频初始化 =====================
def init_audio():
    """初始化MAX98375功放和I2S（参考test_speaker.py）"""
    amp_pin = Pin(AMP_ENABLE_PIN, Pin.OUT)
    amp_pin.value(1)  # 启用功放
    i2s = I2S(
        0,
        sck=Pin(I2S_SCK_PIN),
        ws=Pin(I2S_WS_PIN),
        sd=Pin(I2S_SD_PIN),
        mode=I2S.TX,
        bits=BITS,
        format=I2S.MONO,
        rate=SAMPLE_RATE,
        ibuf=24000  # 与test_speaker.py保持一致
    )
    print("[AUDIO] 音频硬件初始化完成")
    return i2s, amp_pin


def deinit_audio(i2s, amp_pin):
    """清理音频硬件资源"""
    i2s.write(b'\x00\x00' * 100)  # 清空缓冲区
    time.sleep(0.1)
    amp_pin.value(0)
    i2s.deinit()
    print("[AUDIO] 音频硬件已关闭")


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


def extract_base64(row_data):
    base64 = ''
    if 'data":"' in row_data:
        row_data = row_data.split('data":"')[-1]
    if "expires_at" in row_data:
        base64 = row_data.split('","expires')[0]
    else:
        base64 = row_data
    return base64


# ===================== TTS API请求（带实时播放） =====================
def tts_api_request(text):
    """
    核心函数：请求TTS API并实时播放音频
    返回: (success: bool, total_audio_chunks: int, validation_results: list)
    """
    # 1. WiFi连接检查
    if not connect_wifi():
        return False, 0, []

    # 2. 初始化音频
    i2s, amp_pin = init_audio()
    buf_size = 4096  # 与test_speaker.py缓冲区大小一致
    play_buf = bytearray(buf_size)
    sock = None
    audio_chunks = 0
    validation_results = []
    response_received = False

    # 2. 建立SSL连接
    print(f"[API] 连接TTS API: {API_HOST}:{API_PORT}")
    addr_info = socket.getaddrinfo(API_HOST, API_PORT)[0]
    sock = socket.socket(addr_info[0], addr_info[1], addr_info[2])
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

    cnt = 0
    x = []
    while True:
        chunk = sock.read(1024)
        print(f'第{cnt}次\n')
        cnt += 1
        if not chunk:
            break
        row_data = chunk.decode('utf-8', 'ignore')
        base64 = extract_base64(row_data)
        # x.append(base64)
    # filename = f"temp.txt"
    # with open(filename, "w") as f:
    #     for i, text in enumerate(x):
    #         f.write(f"\n第{i}次")
    #         f.write(text)

        # 跳过过短的数据（不完整的数据）
        if len(base64) < 50:
            continue


        audio_bytes = base64_decode(base64)
        print(f"[AUDIO] 解码音频数据，大小: {len(audio_bytes)} 字节")

        # I2S播放（参考test_speaker.py的播放逻辑）
        offset = 0
        while offset < len(audio_bytes):
            chunk_len = min(buf_size, len(audio_bytes) - offset)
            # 确保是偶数长度（16位=2字节/样本）
            if chunk_len % 2 != 0:
                chunk_len -= 1
            if chunk_len <= 0:
                break

            play_buf[:chunk_len] = audio_bytes[offset:offset + chunk_len]
            written = 0
            while written < chunk_len:
                written += i2s.write(play_buf, chunk_len)
            offset += chunk_len
        print(f"[AUDIO] 播放完成音频块 #{audio_chunks}")

    return True, audio_chunks


# ===================== 主程序 =====================
def main():
    """主程序入口"""
    print("\n" + "=" * 50)
    print("ESP32 TTS 流式播放程序")
    print("=" * 50)

    success, audio_chunks = tts_api_request(TEXT)

    if success:
        print("\n[结果] API请求成功完成")


if __name__ == "__main__":
    main()





