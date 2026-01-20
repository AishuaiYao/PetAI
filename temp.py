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
TEXT = "中国国家统计局1月19日发布了2025年全国GDP初步数据。数据显示，2025年，按照可比价格计算，中国大陆实际GDP同比增长5.0%，人均实际GDP同比增长5.1%。2025年的中国经济数据，呈现出一幅令人五味杂陈的复杂图景：名义GDP总量历史性地站上140万亿元的台阶，人均GDP触摸到1.4万美元的门槛，这是国力持续积累的明证；然而，另一组数字却投下了长达一个世纪的阴影——全年仅792万新生儿呱呱坠地，年末总人口较上年锐减339万。"
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


def handle_chunk_data(chunk, i2s, count):
    """处理单个音频块并实时播放"""
    if "output" not in chunk:
        return count, False

    if chunk["output"].get("finish_reason") == "stop":
        return count, True

    audio_info = chunk["output"].get("audio", {})
    if "data" in audio_info:
        # 解码Base64音频数据并立即播放
        audio_bytes = ubinascii.a2b_base64(audio_info["data"])
        i2s.write(audio_bytes)
        count += 1
        print(f"✓ 播放块{count}, 大小: {len(audio_bytes)}")

    return count, False


def stream_chunked_data(sock, i2s):
    """流式处理chunked数据：边接收、边解析、边播放"""
    # 用于缓存未解析完成的SSE行
    sse_buffer = ""
    count = 0
    is_done = False

    print("[HTTP] 开始流式处理chunked数据...")

    while not is_done:
        # 1. 读取chunk大小行
        size_line = b""
        while b'\r\n' not in size_line:
            chunk = sock.read(1)
            if not chunk:
                print("[HTTP] 连接中断，结束流式处理")
                return count
            size_line += chunk

        # 2. 解析chunk大小（十六进制）
        chunk_size_str = size_line.split(b'\r\n')[0].strip()
        if not chunk_size_str:
            continue

        try:
            chunk_size = int(chunk_size_str, 16)
        except:
            print(f"[HTTP] chunk大小解析失败: {chunk_size_str}")
            continue

        # 3. chunk大小为0表示结束
        if chunk_size == 0:
            print("[HTTP] 收到结束chunk (size=0)")
            break

        # 4. 读取指定大小的数据（流式读取）
        received = 0
        chunk_data = b""
        while received < chunk_size:
            to_read = min(4096, chunk_size - received)
            data = sock.read(to_read)
            if not data:
                break
            chunk_data += data
            received += len(data)

        print(f"[HTTP] 接收chunk: 大小={chunk_size}, 实际={len(chunk_data)}")

        # 5. 将当前chunk数据转换为字符串并拼接到SSE缓冲区
        sse_buffer += chunk_data.decode('utf-8', 'ignore')

        # 6. 解析SSE缓冲区中的完整行（核心流式解析逻辑）
        # 按换行符分割，只处理完整的行，不完整的留在缓冲区
        lines = sse_buffer.split('\n')
        # 最后一行可能不完整，放回缓冲区
        sse_buffer = lines[-1] if lines else ""

        # 处理所有完整的行
        for line in lines[:-1]:
            line = line.strip()
            if not line:
                continue

            # 解析SSE行
            parsed_line = parse_sse_line(line)
            if not parsed_line:
                continue

            if parsed_line["type"] == "done":
                print("[SSE] 收到[DONE]信号")
                is_done = True
                break

            if parsed_line["type"] == "data":
                count, is_done = handle_chunk_data(parsed_line["data"], i2s, count)
                if is_done:
                    print("[SSE] 收到完成信号")
                    break

        # 7. 读取chunk结尾的\r\n
        sock.read(2)  # 读取\r\n

        # 如果已完成，退出循环
        if is_done:
            break

    # 处理缓冲区中剩余的最后一行数据
    if sse_buffer.strip():
        parsed_line = parse_sse_line(sse_buffer.strip())
        if parsed_line and parsed_line["type"] == "data":
            count, _ = handle_chunk_data(parsed_line["data"], i2s, count)

    return count


# ===================== TTS API请求（流式处理版） =====================
def tts_api_request(text):
    """
    核心函数：请求TTS API并**实时流式播放**音频
    边接收数据、边解析、边播放，降低内存占用
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

    # 7. 流式处理数据（核心修改点）
    total_count = 0
    if "transfer-encoding: chunked" in header_text.lower():
        print("[HTTP] 检测到chunked编码，开始流式处理...")
        # 流式处理chunked数据，边接收边播放
        total_count = stream_chunked_data(sock, i2s)
    else:
        # 兼容非chunked编码（仍做流式处理）
        print("[HTTP] 非chunked编码，开始流式读取...")
        sse_buffer = ""
        count = 0
        while True:
            chunk = sock.read(RECV_BUFFER_SIZE)
            if not chunk:
                break
            sse_buffer += chunk.decode('utf-8', errors='ignore')

            # 解析完整行并播放
            lines = sse_buffer.split('\n')
            sse_buffer = lines[-1] if lines else ""
            for line in lines[:-1]:
                line = line.strip()
                if not line or not line.startswith('data:'):
                    continue

                json_str = line[5:]
                if json_str == '[DONE]':
                    break

                try:
                    parsed = json.loads(json_str)
                    count, is_done = handle_chunk_data(parsed, i2s, count)
                    if is_done:
                        break
                except Exception as e:
                    print(f"[SSE] JSON解析失败: {e}")
                    continue
            total_count = count

    # 8. 关闭资源
    sock.close()
    i2s.deinit()
    Pin(21, Pin.OUT).value(0)
    print(f"[播放] 音频设备已释放，共播放 {total_count} 个音频块")

    return True


# ===================== 主程序 =====================
def main():
    print("\n" + "=" * 50)
    print("ESP32 TTS 流式播放程序 (实时流式处理版)")
    print("=" * 50)

    success = tts_api_request(TEXT)

    if success:
        print("\n✅ 程序执行成功")
    else:
        print("\n❌ 程序执行失败")


if __name__ == "__main__":
    main()