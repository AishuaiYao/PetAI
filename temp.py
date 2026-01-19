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
        ibuf=24000
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


def tts_api_request(text):
    """
    核心函数：请求TTS API并实时播放音频
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

    # 6. 调试：打开日志文件
    debug_file = open("debug_log.txt", "w")
    debug_file.write("=== SSE数据解析调试日志 ===\n\n")

    count = 0
    buffer = ""
    chunk_num = 0
    is_done = False  # 在循环外初始化

    while True:
        chunk = sock.read(RECV_BUFFER_SIZE)
        chunk_num += 1

        if not chunk:
            debug_file.write(f"\n[读取结束] chunk_num={chunk_num}, buffer长度={len(buffer)}\n")
            break

        # 记录原始chunk信息
        debug_file.write(f"\n[Chunk {chunk_num}] 原始长度={len(chunk)}\n")
        debug_file.write(f"[Chunk {chunk_num}] 前100字符: {chunk[:100]}\n")

        buffer += chunk.decode('utf-8')
        debug_file.write(f"[Chunk {chunk_num}] 处理后buffer长度={len(buffer)}\n")

        line_counter = 0
        while '\n' in buffer:
            line_counter += 1
            line, buffer = buffer.split('\n', 1)
            original_line = line  # 保存原始行

            debug_file.write(f"\n  [Line {line_counter}] 分割前buffer长度={len(buffer) + len(line) + 1}\n")
            debug_file.write(f"  [Line {line_counter}] line长度={len(line)}\n")
            debug_file.write(f"  [Line {line_counter}] line内容: {repr(line)}\n")

            line = line.strip()
            debug_file.write(f"  [Line {line_counter}] strip后: {repr(line)}\n")

            if not line:
                debug_file.write(f"  [Line {line_counter}] 跳过空行\n")
                continue

            parsed = parse_sse_line(line)
            debug_file.write(f"  [Line {line_counter}] parsed类型: {type(parsed)}\n")

            if parsed is None:
                debug_file.write(f"  [Line {line_counter}] 不是SSE数据行\n")
                continue

            count += 1
            debug_file.write(f"  [Line {line_counter}] 有效数据块计数={count}\n")

            if parsed["type"] == "done":
                debug_file.write(f"  [Line {line_counter}] 收到[DONE]信号\n")
                is_done = True
                break

            audio_data, is_done = handle_chunk_data(parsed["data"])  # 这里会更新is_done
            debug_file.write(f"  [Line {line_counter}] audio_data存在: {audio_data is not None}\n")
            debug_file.write(f"  [Line {line_counter}] is_done: {is_done}\n")

            if audio_data:
                audio_bytes = ubinascii.a2b_base64(audio_data)
                debug_file.write(f"  [Line {line_counter}] base64解码后大小={len(audio_bytes)}\n")
                debug_file.write(f"  [Line {line_counter}] 前10字节: {audio_bytes[:10].hex()}\n")

                try:
                    i2s.write(audio_bytes)
                    debug_file.write(f"  [Line {line_counter}] I2S写入成功\n")
                    print(f"✓ 播放块{count}, 大小: {len(audio_bytes)}")
                except Exception as e:
                    debug_file.write(f"  [Line {line_counter}] I2S写入失败: {e}\n")

        debug_file.write(f"\n[Chunk {chunk_num}] 处理完成，剩余buffer长度={len(buffer)}\n")
        debug_file.write(f"[Chunk {chunk_num}] 剩余buffer内容: {repr(buffer[:100])}\n")

        if is_done:
            debug_file.write(f"[Chunk {chunk_num}] 检测到is_done=True，结束循环\n")
            break

    debug_file.write(f"\n=== 统计信息 ===\n")
    debug_file.write(f"总chunk数: {chunk_num}\n")
    debug_file.write(f"总数据块数: {count}\n")
    debug_file.write(f"最终buffer长度: {len(buffer)}\n")
    debug_file.write(f"最终buffer内容: {repr(buffer)}\n")

    debug_file.close()
    sock.close()

    print(f"共获取 {count} 条数据")
    print(f"调试日志已保存到 debug_log.txt")

    # 关闭I2S
    i2s.deinit()
    Pin(21, Pin.OUT).value(0)


# ===================== 主程序 =====================
def main():
    print("\n" + "=" * 50)
    print("ESP32 TTS 流式播放程序 (调试版)")
    print("=" * 50)

    tts_api_request(TEXT)


if __name__ == "__main__":
    main()





























