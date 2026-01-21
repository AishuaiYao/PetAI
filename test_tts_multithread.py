import socket
import json
import time
import network
import ubinascii
import _thread
from machine import I2S, Pin

# ===================== 核心配置 =====================
WIFI_SSID = "CMCC-huahua"
WIFI_PASSWORD = "*HUAHUAshi1zhimao"
API_KEY = 'sk-943f95da67d04893b70c02be400e2935'
TEXT = "中国国家统计局1月19日发布了2025年全国GDP初步数据。数据显示，2025年，按照可比价格计算，中国大陆实际GDP同比增长5.0%，人均实际GDP同比增长5.1%。2025年的中国经济数据，呈现出一幅令人五味杂陈的复杂图景：名义GDP总量历史性地站上140万亿元的台阶，人均GDP触摸到1.4万美元的门槛，这是国力持续积累的明证；然而，另一组数字却投下了长达一个世纪的阴影——全年仅792万新生儿呱呱坠地，年末总人口较上年锐减339万。"
VOICE = "Cherry"
LANGUAGE = "Chinese"
RECV_BUFFER_SIZE = 8192

API_HOST = "dashscope.aliyuncs.com"
API_PORT = 443
API_PATH = "/api/v1/services/aigc/multimodal-generation/generation"

# ===================== 线程通信变量 =====================
audio_buffer = []  # 音频数据缓冲区
buffer_lock = _thread.allocate_lock()  # 缓冲区锁
buffer_not_empty = _thread.allocate_lock()  # 条件变量：缓冲区非空
buffer_not_full = _thread.allocate_lock()  # 条件变量：缓冲区未满
playback_finished = False
BUFFER_SIZE = 10  # 缓冲区大小

# 初始化条件变量
buffer_not_empty.acquire()
buffer_not_full.acquire()


# ===================== WiFi连接 =====================
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if wlan.isconnected():
        print("[WiFi] 已连接")
        return True

    print(f"[WiFi] 连接: {WIFI_SSID}")
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)

    timeout = 15
    while timeout > 0:
        if wlan.isconnected():
            print(f"[WiFi] 成功, IP: {wlan.ifconfig()[0]}")
            return True
        timeout -= 1
        time.sleep(1)
        print(f"[WiFi] 连接中...剩余{timeout}秒")

    print("[WiFi] 连接失败")
    return False


# ===================== 音频播放线程 =====================
def audio_player_thread():
    """线程2：从缓冲区读取音频数据并播放"""
    global playback_finished

    print("[播放器] 音频播放线程启动")

    # 初始化I2S
    Pin(21, Pin.OUT).value(1)
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

    chunk_count = 0

    while True:
        # 等待缓冲区有数据
        try:
            buffer_not_empty.acquire()
        except:
            # 超时或中断
            if playback_finished:
                break
            continue

        with buffer_lock:
            if not audio_buffer:
                # 缓冲区为空，继续等待
                continue

            # 从缓冲区取出音频数据
            audio_data = audio_buffer.pop(0)

            # 通知生产者缓冲区有空位
            try:
                buffer_not_full.release()
            except:
                pass

        # 检查结束信号
        if audio_data is None:
            print("[播放器] 收到结束信号")
            break

        # 播放音频
        try:
            i2s.write(audio_data)
            chunk_count += 1
            print(f"[播放器] 播放块{chunk_count}, 大小: {len(audio_data)}")
        except Exception as e:
            print(f"[播放器] 播放错误: {e}")
            break

    # 清理资源
    i2s.deinit()
    Pin(21, Pin.OUT).value(0)
    print(f"[播放器] 播放结束，共播放 {chunk_count} 个音频块")


# ===================== 缓冲区管理 =====================
def put_audio_data(audio_data):
    """将音频数据放入缓冲区"""
    global playback_finished

    while not playback_finished:
        with buffer_lock:
            if len(audio_buffer) < BUFFER_SIZE:
                audio_buffer.append(audio_data)

                # 通知消费者有数据可用
                try:
                    buffer_not_empty.release()
                except:
                    pass
                return True

        # 缓冲区满，等待
        try:
            buffer_not_full.acquire(timeout=0.1)
        except:
            if playback_finished:
                return False

    return False


def signal_playback_finished():
    """发送播放结束信号"""
    global playback_finished
    playback_finished = True

    with buffer_lock:
        # 清空缓冲区并发送结束信号
        audio_buffer.clear()
        audio_buffer.append(None)

        # 通知消费者
        try:
            buffer_not_empty.release()
        except:
            pass

        # 通知生产者
        try:
            buffer_not_full.release()
        except:
            pass


# ===================== 数据接收线程 =====================
def data_receiver_thread(text):
    """线程1：接收TTS API数据并放入缓冲区"""
    global playback_finished

    print("[接收器] 数据接收线程启动")

    if not connect_wifi():
        signal_playback_finished()
        return

    # 建立SSL连接
    print(f"[API] 连接: {API_HOST}:{API_PORT}")
    addr_info = socket.getaddrinfo(API_HOST, API_PORT)[0]
    sock = socket.socket(addr_info[0], addr_info[1], addr_info[2])
    sock.setsockopt(1, 8, RECV_BUFFER_SIZE)
    sock.settimeout(15)
    sock.connect(addr_info[-1])

    import ssl
    sock = ssl.wrap_socket(sock, server_hostname=API_HOST)
    print("[API] SSL连接成功")

    # 构建请求
    payload_dict = {
        "model": "qwen3-tts-flash",
        "input": {"text": text},
        "parameters": {
            "voice": VOICE,
            "language_type": LANGUAGE
        }
    }
    payload = json.dumps(payload_dict)

    # 发送请求
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
    print(f"[API] 请求已发送，文本长度: {len(text)}")

    # 接收HTTP响应头部
    print("[HTTP] 接收响应头部...")
    headers = b""
    while b'\r\n\r\n' not in headers:
        chunk = sock.read(1)
        if not chunk:
            print("[HTTP] 连接中断")
            signal_playback_finished()
            sock.close()
            return
        headers += chunk

    header_text = headers.decode('utf-8')

    if "200 OK" not in header_text:
        print(f"[HTTP] 错误: {header_text[:100]}")
        signal_playback_finished()
        sock.close()
        return

    # 流式解析数据
    print("[接收器] 开始流式解析数据...")
    sse_buffer = ""

    try:
        while not playback_finished:
            # 读取数据
            data = sock.read(4096)
            if not data:
                break

            sse_buffer += data.decode('utf-8', 'ignore')

            # 解析SSE格式数据
            lines = sse_buffer.split('\n')
            # 保留不完整的行
            sse_buffer = lines[-1]

            for line in lines[:-1]:
                line = line.strip()
                if not line.startswith('data:'):
                    continue

                json_str = line[5:]
                if json_str == '[DONE]':
                    print("[接收器] 收到结束信号[DONE]")
                    continue

                try:
                    parsed = json.loads(json_str)

                    # 检查是否结束
                    if parsed.get("output", {}).get("finish_reason") == "stop":
                        print("[接收器] 收到stop信号")
                        break

                    # 提取音频数据
                    audio_info = parsed.get("output", {}).get("audio", {})
                    if "data" in audio_info:
                        audio_bytes = ubinascii.a2b_base64(audio_info["data"])

                        # 将音频数据放入缓冲区
                        if not put_audio_data(audio_bytes):
                            break
                        print(f"[接收器] 音频块入队, 大小: {len(audio_bytes)}")

                except Exception as e:
                    print(f"[接收器] 解析错误: {e}")
                    continue
    except Exception as e:
        print(f"[接收器] 发生错误: {e}")

    # 发送结束信号
    signal_playback_finished()
    sock.close()
    print("[接收器] 数据接收线程结束")


# ===================== 主程序 =====================
def main():
    print("\n" + "=" * 50)
    print("ESP32 TTS 双线程流式播放程序")
    print("=" * 50)

    try:
        # 启动音频播放线程
        _thread.start_new_thread(audio_player_thread, ())

        # 等待一小段时间确保播放线程启动
        time.sleep(0.5)

        # 启动数据接收线程（在主线程中运行）
        data_receiver_thread(TEXT)

        # 等待播放完成
        while not playback_finished:
            time.sleep(0.1)

        print("\n✅ 程序执行完成")
    except Exception as e:
        print(f"\n❌ 程序执行失败: {e}")
        signal_playback_finished()


if __name__ == "__main__":
    main()
