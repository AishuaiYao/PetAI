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
    Pin(21, Pin.OUT).value(1)  # 启用功放
    i2s = I2S(
        0,
        sck=Pin(9),
        ws=Pin(10),
        sd=Pin(8),
        mode=I2S.TX,
        bits=16,
        format=I2S.MONO,
        rate=24000,
        ibuf=48000
    )
    return i2s


# ===================== WiFi连接 =====================
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if wlan.isconnected():
        print("[WiFi] 已连接WiFi，跳过重连")
        print(f"[WiFi] IP地址: {wlan.ifconfig()[0]}")
        return True

    print(f"[WiFi] 正在连接WiFi: {WIFI_SSID}")
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)

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
    if "output" not in chunk:
        return None, False

    if chunk["output"].get("finish_reason") == "stop":
        return None, True

    audio_info = chunk["output"].get("audio", {})
    if "data" in audio_info:
        return audio_info["data"], False

    return None, False


def decode_chunked_data(sock):
    """解码HTTP chunked传输编码的数据"""
    buffer = b""

    print("[HTTP] 开始解码chunked数据...")

    while True:
        # 1. 读取chunk大小行
        size_line = b""
        while b'\r\n' not in size_line:
            chunk = sock.read(1)
            if not chunk:
                return buffer
            size_line += chunk

        # 2. 解析chunk大小（十六进制）
        chunk_size_str = size_line.split(b'\r\n')[0].strip()
        if not chunk_size_str:
            continue

        try:
            chunk_size = int(chunk_size_str, 16)
        except:
            print(f"[HTTP] chunk大小解析失败: {chunk_size_str}")
            break

        # 3. chunk大小为0表示结束
        if chunk_size == 0:
            print("[HTTP] 收到结束chunk (size=0)")
            break

        # 4. 读取指定大小的数据
        received = 0
        chunk_data = b""
        while received < chunk_size:
            to_read = min(4096, chunk_size - received)
            data = sock.read(to_read)
            if not data:
                break
            chunk_data += data
            received += len(data)

        buffer += chunk_data
        print(f"[HTTP] 读取chunk: 大小={chunk_size}, 实际={len(chunk_data)}")

        # 5. 读取结尾的\r\n
        sock.read(2)  # 读取\r\n

    return buffer


# ===================== TTS API请求（修复HTTP chunked编码问题） =====================
def tts_api_request(text):
    """
    核心函数：请求TTS API并实时播放音频
    修复了HTTP chunked传输编码问题
    """
    # 1. WiFi连接检查
    if not connect_wifi():
        return False

    # 2. 初始化音频
    i2s = init_audio()

    # 3. 建立SSL连接
    print(f"[API] 连接TTS API: {API_HOST}:{API_PORT}")
    addr_info = socket.getaddrinfo(API_HOST, API_PORT)[0]
    sock = socket.socket(addr_info[0], addr_info[1], addr_info[2])
    sock.setsockopt(1, 8, RECV_BUFFER_SIZE)

    sock.settimeout(15)
    sock.connect(addr_info[-1])

    import ssl
    sock = ssl.wrap_socket(sock, server_hostname=API_HOST)
    print("[API] SSL连接建立成功")

    # 4. 构建请求
    payload_dict = {
        "model": "qwen3-tts-flash",
        "input": {"text": text},
        "parameters": {
            "voice": VOICE,
            "language_type": LANGUAGE
        }
    }
    payload = json.dumps(payload_dict)

    # 5. 发送请求
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

    # 6. 接收HTTP响应头部
    print("[HTTP] 接收响应头部...")
    headers = b""
    while b'\r\n\r\n' not in headers:
        chunk = sock.read(1)
        if not chunk:
            print("[HTTP] 连接中断")
            sock.close()
            i2s.deinit()
            Pin(21, Pin.OUT).value(0)
            return False
        headers += chunk

    header_text = headers.decode('utf-8')
    print(f"[HTTP] 头部接收完成 ({len(headers)} 字节)")

    # 检查HTTP状态码
    if "200 OK" not in header_text:
        print(f"[HTTP] 错误响应: {header_text[:100]}")
        sock.close()
        i2s.deinit()
        Pin(21, Pin.OUT).value(0)
        return False

    # 7. 处理chunked编码
    if "transfer-encoding: chunked" in header_text.lower():
        print("[HTTP] 检测到chunked编码，开始解码...")
        # 解码chunked数据
        sse_raw_data = decode_chunked_data(sock)
        print(f"[HTTP] 解码完成，获得 {len(sse_raw_data)} 字节SSE数据")

        # 将二进制数据转换为字符串
        buffer = sse_raw_data.decode('utf-8', 'ignore')
    else:
        # 非chunked编码，直接读取
        print("[HTTP] 非chunked编码，直接读取数据...")
        buffer = ""
        while True:
            chunk = sock.read(RECV_BUFFER_SIZE)
            if not chunk:
                break
            buffer += chunk.decode('utf-8', errors='ignore')

    sock.close()

    # 8. 解析SSE数据并播放
    print("[SSE] 开始解析SSE数据...")
    count = 0
    is_done = False

    # 逐行解析buffer
    lines = buffer.split('\n')
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue

        if line.startswith('data:'):
            json_str = line[5:]

            if json_str == '[DONE]':
                print("[SSE] 收到[DONE]信号")
                break

            try:
                parsed = json.loads(json_str)
                count += 1

                audio_data, is_done = handle_chunk_data(parsed)
                if audio_data:
                    audio_bytes = ubinascii.a2b_base64(audio_data)
                    i2s.write(audio_bytes)
                    print(f"✓ 播放块{count}, 大小: {len(audio_bytes)}")

                if is_done:
                    print("[SSE] 收到完成信号")
                    break

            except Exception as e:
                print(f"[SSE] JSON解析失败: {e}")
                continue

    print(f"[SSE] 解析完成，共处理 {count} 个音频块")

    # 9. 关闭资源
    i2s.deinit()
    Pin(21, Pin.OUT).value(0)
    print("[播放] 音频设备已释放")

    return True


# ===================== 主程序 =====================
def main():
    print("\n" + "=" * 50)
    print("ESP32 TTS 流式播放程序 (修复chunked编码)")
    print("=" * 50)

    success = tts_api_request(TEXT)

    if success:
        print("\n✅ 程序执行成功")
    else:
        print("\n❌ 程序执行失败")


if __name__ == "__main__":
    main()

    # E:\PetAI\Project\.venv\Scripts\python.exe
    # E:\PetAI\Project\example\qwen_demo\tts_request.py
    # 正在请求
    # URL: https: // dashscope.aliyuncs.com / api / v1 / services / aigc / multimodal - generation / generation
    # 响应状态码: 200
    # 请求成功，开始接收音频流...
    # ✓ 播放音频块，大小: 7680
    # samples
    # ✓ 播放音频块，大小: 7680
    # samples
    # ✓ 播放音频块，大小: 7680
    # samples
    # ✓ 播放音频块，大小: 7680
    # samples
    # ✓ 播放音频块，大小: 7680
    # samples
    # ✓ 播放音频块，大小: 7680
    # samples
    # ✓ 播放音频块，大小: 7680
    # samples
    # ✓ 播放音频块，大小: 7680
    # samples
    # ✓ 播放音频块，大小: 7680
    # samples
    # ✓ 播放音频块，大小: 7680
    # samples
    # ✓ 播放音频块，大小: 7680
    # samples
    # ✓ 播放音频块，大小: 0
    # samples
    # ✓ 流式传输完成
    # 共获取
    # 13
    # 条数据
    # 数据已保存到.. /../ data / tts_stream_data.json
    # 音频播放完成，资源已清理
    #
    # 进程已结束，退出代码为
    # 0

