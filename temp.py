import socket
import json
import time
import network
import ubinascii
import _thread
from machine import I2S, Pin

# ===================== 核心配置 =====================
# --- 配置 ---
WIFI_SSID = "CMCC-huahua"
WIFI_PASSWORD = "*HUAHUAshi1zhimao"
API_KEY = 'sk-943f95da67d04893b70c02be400e2935'
TEXT = "我是电子花花，你听的到吗"
TEXT = "中国国家统计局1月19日发布了2025年全国GDP初步数据。数据显示，2025年，按照可比价格计算，中国大陆实际GDP同比增长5.0%，人均实际GDP同比增长5.1%。"
VOICE = "Cherry"
LANGUAGE = "Chinese"
RECV_BUFFER_SIZE = 81920

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

# ===================== 共享变量 =====================
audio_buffer = []  # 音频数据缓冲区
buffer_lock = _thread.allocate_lock()  # 保护buffer的锁
receiving_complete = False  # 标记接收线程是否已完成所有工作


# ===================== WiFi连接 =====================
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)

    timeout = 15
    while not wlan.isconnected() and timeout > 0:
        time.sleep(1)
        timeout -= 1

    if wlan.isconnected():
        print(f"WiFi连接成功: {wlan.ifconfig()[0]}")
        return True
    else:
        print("WiFi连接失败")
        return False


# ===================== 音频播放线程 =====================
def audio_player():
    print("音频播放线程启动")
    time.sleep(1)
    # 初始化I2S
    Pin(21, Pin.OUT).value(1)
    audio_out = I2S(
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

    chunk_count = 0

    while True:

        with buffer_lock:
            if audio_buffer:
                audio_chunk = audio_buffer.pop(0)
                print(f"[audio]播放音频块{chunk_count + 1} 大小: {len(audio_chunk)}, 缓冲区剩余: {len(audio_buffer)} 块")
            elif receiving_complete:
                # 接收已完成且缓冲区为空 -> 所有数据都播放完了
                print("播放线程检测到接收完成且缓冲区为空，准备退出")
                break
            else:
                # 缓冲区为空但接收未完成，打印状态
                audio_chunk = None

        # 在锁外播放音频，避免阻塞接收线程
        if audio_chunk is not None:
            audio_out.write(audio_chunk)
            chunk_count += 1

    # 清理
    # audio_out.deinit()
    # Pin(21, Pin.OUT).value(0)
    print(f"播放完成，共播放 {chunk_count} 个音频块")


# ===================== 数据接收线程 =====================
def receive_audio_data(text):
    print("数据接收线程启动")

    if not connect_wifi():
        return

    # 3. 建立SSL连接
    print(f"[API] 连接TTS API: {API_HOST}:{API_PORT}")
    addr_info = socket.getaddrinfo(API_HOST, API_PORT)[0]
    sock = socket.socket(addr_info[0], addr_info[1], addr_info[2])
    sock.setsockopt(1, 8, RECV_BUFFER_SIZE)

    sock.settimeout(30)
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
            Pin(21, Pin.OUT).value(0)
            return False
        headers += chunk

    header_text = headers.decode('utf-8')
    print(f"[HTTP] 头部接收完成 ({len(headers)} 字节)")

    # 检查HTTP状态码
    if "200 OK" not in header_text:
        print(f"[HTTP] 错误响应: {header_text[:100]}")
        sock.close()
        Pin(21, Pin.OUT).value(0)
        return False

    # 7. 流式处理数据（核心修改点）
    total_count = 0
    if "transfer-encoding: chunked" in header_text.lower():
        print("[HTTP] 检测到chunked编码，开始流式处理...")
        # 流式处理chunked数据，边接收边播放
        total_count = stream_chunked_data(sock)



    print(f"共接收了 {total_count} 个音频块")

    global  receiving_complete
    with buffer_lock:
        receiving_complete = True

    return True


def stream_chunked_data(sock):
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

        # 4. 边读取边解析，避免阻塞播放线程
        received = 0
        while received < chunk_size:
            # 每次只读取一小块数据，避免长时间阻塞
            to_read = min(1024, chunk_size - received)
            data = sock.read(to_read)
            if not data:
                break

            # 5. 立即将读取的数据追加到SSE缓冲区并解码
            chunk_data_str = data.decode('utf-8', 'ignore')
            sse_buffer += chunk_data_str
            received += len(data)

            # 6. 立即解析缓冲区中的完整行，边解析边放入播放buffer
            while '\n' in sse_buffer:
                # 提取第一行
                line_end = sse_buffer.find('\n')
                line = sse_buffer[:line_end]
                sse_buffer = sse_buffer[line_end + 1:]

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
                    count, is_done = handle_chunk_data(parsed_line["data"], count)
                    if is_done:
                        print("[SSE] 收到完成信号")
                        break

            # 如果收到完成信号，提前结束读取
            if is_done:
                # 读取剩余的chunk数据以保持HTTP协议正确性
                remaining = chunk_size - received
                if remaining > 0:
                    sock.read(remaining)
                    received = chunk_size
                break

        # print(f"[HTTP] 接收chunk: 大小={chunk_size}, 实际={received}")

        # 7. 读取chunk结尾的\r\n
        sock.read(2)  # 读取\r\n

        # 如果已完成，退出循环
        if is_done:
            break

    # 处理缓冲区中剩余的最后一行数据
    if sse_buffer.strip():
        parsed_line = parse_sse_line(sse_buffer.strip())
        if parsed_line and parsed_line["type"] == "data":
            count, _ = handle_chunk_data(parsed_line["data"], count)

    return count



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


def handle_chunk_data(chunk, count):
    """处理单个音频块并实时播放"""

    if "output" not in chunk:
        return count, False

    if chunk["output"].get("finish_reason") == "stop":
        return count, True

    audio_info = chunk["output"].get("audio", {})
    if "data" in audio_info:
        # 解码音频数据
        audio_bytes = ubinascii.a2b_base64(audio_info["data"])

        # 添加到播放缓冲区
        with buffer_lock:
            audio_buffer.append(audio_bytes)
        count += 1
        print(f"[HTTP] base64的数据长度{len(audio_info['data'])} 解码后二进制数据长度{len(audio_bytes)} 缓冲区大小{len(audio_buffer)} ")
    return count, False


# ===================== 主程序 =====================
def main():
    print("\n=== ESP32 TTS 流式播放 ===")

    # 启动播放线程
    _thread.start_new_thread(audio_player, ())


    # 在主线程中运行接收函数
    receive_audio_data(TEXT)

    # 等待接收完成，并且缓冲区播放完毕
    while True:
        with buffer_lock:
            buffer_empty = len(audio_buffer) == 0
            all_done = receiving_complete and buffer_empty
        if all_done:
            break
        time.sleep(1)

    print("程序执行完成")


if __name__ == "__main__":
    main()