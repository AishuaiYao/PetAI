import socket
import json
import struct
import time
import network
import ubinascii
import _thread  # ESP32 MicroPython 线程模块

from machine import I2S, Pin

# ===================== 核心配置 =====================
# WiFi配置
WIFI_SSID = "CMCC-huahua"
WIFI_PASSWORD = "*HUAHUAshi1zhimao"
# API配置
API_KEY = 'sk-943f95da67d04893b70c02be400e2935'
TEXT = "我是电子花花，你听的到吗"
TEXT = "中国国家统计局1月19日发布了2025年全国GDP初步数据。数据显示，2025年，按照可比价格计算，中国大陆实际GDP同比增长5.0%，人均实际GDP同比增长5.1%。2025年的中国经济数据，呈现出一幅令人五味杂陈的复杂图景：名义GDP总量历史性地站上140万亿元的台阶，人均GDP触摸到1.4万美元的门槛，这是国力持续积累的明证；然而，另一组数字却投下了长达一个世纪的阴影——全年仅792万新生儿呱呱坠地，年末总人口较上年锐减339万。"

VOICE = "Cherry"
LANGUAGE = "Chinese"
RECV_BUFFER_SIZE = 8192
API_HOST = "dashscope.aliyuncs.com"
API_PORT = 443
API_PATH = "/api/v1/services/aigc/multimodal-generation/generation"
# I2S音频配置
I2S_SCK_PIN = 9
I2S_WS_PIN = 10
I2S_SD_PIN = 8
AMP_ENABLE_PIN = 21
SAMPLE_RATE = 24000
BITS = 16
CHANNELS = 1
# 双线程缓冲配置（核心优化）
AUDIO_QUEUE = []          # 音频数据队列（生产者放，消费者取）
QUEUE_MAX_SIZE = 10       # 队列最大缓冲块数（防止内存溢出）
QUEUE_MIN_PRELOAD = 2     # 预加载至少2块数据再开始播放（避免初期卡顿）
QUEUE_LOCK = _thread.allocate_lock()  # 线程安全锁
PLAY_FINISH_FLAG = False  # 播放完成标志
ERROR_FLAG = False        # 错误标志

# ===================== 工具函数 =====================
def connect_wifi():
    """WiFi连接（复用原有逻辑）"""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected():
        print("[WiFi] 已连接WiFi，IP: {}".format(wlan.ifconfig()[0]))
        return True
    print(f"[WiFi] 正在连接 {WIFI_SSID}")
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)
    timeout = 15
    while timeout > 0:
        if wlan.isconnected():
            print(f"[WiFi] 连接成功，IP: {wlan.ifconfig()[0]}")
            return True
        timeout -= 1
        time.sleep(0.5)
    print("[WiFi] 连接失败")
    return False

def parse_sse_line(line_str):
    """解析单条SSE行（复用原有逻辑）"""
    if not line_str.startswith('data:'):
        return None
    json_str = line_str[5:].strip()
    if json_str == '[DONE]':
        return {"type": "done"}
    try:
        return {"type": "data", "data": json.loads(json_str)}
    except:
        return None

# ===================== 生产者线程：拉取音频数据 =====================
def producer_thread(sock):
    """
    生产者线程：负责接收API的chunked数据，解析音频后放入队列
    sock: 已建立的SSL连接套接字
    """
    global PLAY_FINISH_FLAG, ERROR_FLAG
    sse_buffer = ""
    chunk_count = 0

    print("[生产者] 开始接收并解析音频数据...")
    try:
        while not PLAY_FINISH_FLAG and not ERROR_FLAG:
            # 1. 读取chunk大小行
            size_line = b""
            while b'\r\n' not in size_line:
                chunk = sock.read(1)
                if not chunk:
                    print("[生产者] 连接中断")
                    ERROR_FLAG = True
                    return
                size_line += chunk

            # 2. 解析chunk大小
            chunk_size_str = size_line.split(b'\r\n')[0].strip()
            if not chunk_size_str:
                continue
            try:
                chunk_size = int(chunk_size_str, 16)
            except:
                print(f"[生产者] chunk大小解析失败: {chunk_size_str}")
                continue

            # 3. chunk为0表示结束
            if chunk_size == 0:
                print("[生产者] 数据接收完成")
                break

            # 4. 读取chunk数据
            received = 0
            chunk_data = b""
            while received < chunk_size:
                to_read = min(4096, chunk_size - received)
                data = sock.read(to_read)
                if not data:
                    break
                chunk_data += data
                received += len(data)

            # 5. 解析SSE数据并提取音频
            sse_buffer += chunk_data.decode('utf-8', 'ignore')
            lines = sse_buffer.split('\n')
            sse_buffer = lines[-1] if lines else ""  # 保留未完成的行

            for line in lines[:-1]:
                line = line.strip()
                if not line:
                    continue
                parsed = parse_sse_line(line)
                if not parsed:
                    continue

                if parsed["type"] == "done":
                    PLAY_FINISH_FLAG = True
                    break

                if parsed["type"] == "data":
                    audio_info = parsed["data"].get("output", {}).get("audio", {})
                    if "data" in audio_info:
                        # 解码Base64音频数据
                        audio_bytes = ubinascii.a2b_base64(audio_info["data"])
                        chunk_count += 1

                        # 线程安全地放入队列（加锁防止冲突）
                        with QUEUE_LOCK:
                            if len(AUDIO_QUEUE) < QUEUE_MAX_SIZE:
                                AUDIO_QUEUE.append(audio_bytes)
                                print(f"[生产者] 放入队列第{chunk_count}块，队列当前大小: {len(AUDIO_QUEUE)}")
                            else:
                                print(f"[生产者] 队列已满，等待...")
                                time.sleep(0.05)  # 队列满时短暂等待

            # 读取chunk结尾的\r\n
            sock.read(2)

    except Exception as e:
        print(f"[生产者] 异常: {e}")
        ERROR_FLAG = True
    finally:
        PLAY_FINISH_FLAG = True
        print("[生产者] 线程结束")

# ===================== 消费者线程：播放音频 =====================
def consumer_thread():
    """
    消费者线程：专门从队列读取音频数据，通过I2S播放
    核心：只负责播放，不处理网络，避免卡顿
    """
    global ERROR_FLAG
    # 初始化音频设备
    Pin(AMP_ENABLE_PIN, Pin.OUT).value(1)
    i2s = I2S(
        0,
        sck=Pin(I2S_SCK_PIN),
        ws=Pin(I2S_WS_PIN),
        sd=Pin(I2S_SD_PIN),
        mode=I2S.TX,
        bits=BITS,
        format=I2S.MONO,
        rate=SAMPLE_RATE,
        ibuf=10000  # 增大内部缓冲区，进一步减少卡顿
    )
    play_count = 0

    print("[消费者] 等待预加载音频数据...")
    # 预加载：等待队列有足够数据再开始播放（避免初期卡顿）
    while len(AUDIO_QUEUE) < QUEUE_MIN_PRELOAD and not ERROR_FLAG:
        time.sleep(0.05)

    if ERROR_FLAG:
        print("[消费者] 预加载阶段出错，退出")
        i2s.deinit()
        Pin(AMP_ENABLE_PIN, Pin.OUT).value(0)
        return

    print("[消费者] 开始播放音频...")
    try:
        while not PLAY_FINISH_FLAG or len(AUDIO_QUEUE) > 0:
            # 线程安全地从队列取数据
            with QUEUE_LOCK:
                if len(AUDIO_QUEUE) > 0:
                    audio_bytes = AUDIO_QUEUE.pop(0)  # 取队列头部（先进先出）
                else:
                    audio_bytes = None

            if audio_bytes:
                # 播放音频（I2S.write是阻塞的，但此时队列已有缓冲，不影响）
                i2s.write(audio_bytes)
                play_count += 1
                print(f"[消费者] 播放第{play_count}块，剩余队列: {len(AUDIO_QUEUE)}")
            else:
                # 队列空时短暂等待，避免空轮询占用CPU
                time.sleep(0.01)

        # 播放完所有数据后，清空I2S缓冲区
        i2s.flush()
        print(f"[消费者] 播放完成，共播放{play_count}块")

    except Exception as e:
        print(f"[消费者] 播放异常: {e}")
        ERROR_FLAG = True
    finally:
        # 释放音频资源
        i2s.deinit()
        Pin(AMP_ENABLE_PIN, Pin.OUT).value(0)
        print("[消费者] 线程结束")

# ===================== 核心TTS请求函数 =====================
def tts_api_request(text):
    """主函数：初始化连接，启动双线程"""
    global PLAY_FINISH_FLAG, ERROR_FLAG, AUDIO_QUEUE
    # 重置全局状态
    PLAY_FINISH_FLAG = False
    ERROR_FLAG = False
    AUDIO_QUEUE = []

    # 1. 检查WiFi
    if not connect_wifi():
        return False

    # 2. 建立SSL连接
    print(f"[API] 连接 {API_HOST}:{API_PORT}")
    try:
        addr_info = socket.getaddrinfo(API_HOST, API_PORT)[0]
        sock = socket.socket(addr_info[0], addr_info[1], addr_info[2])
        sock.setsockopt(1, 8, RECV_BUFFER_SIZE)
        sock.settimeout(15)
        sock.connect(addr_info[-1])
        sock = ssl.wrap_socket(sock, server_hostname=API_HOST)
    except Exception as e:
        print(f"[API] 连接失败: {e}")
        return False

    # 3. 构建并发送请求
    payload = json.dumps({
        "model": "qwen3-tts-flash",
        "input": {"text": text},
        "parameters": {"voice": VOICE, "language_type": LANGUAGE}
    })
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
    try:
        sock.write(request_headers.encode('utf-8'))
        sock.write(payload_bytes)
    except Exception as e:
        print(f"[API] 发送请求失败: {e}")
        sock.close()
        return False

    # 4. 接收响应头部
    print("[HTTP] 接收响应头部...")
    headers = b""
    try:
        while b'\r\n\r\n' not in headers:
            chunk = sock.read(1)
            if not chunk:
                print("[HTTP] 头部接收中断")
                sock.close()
                return False
            headers += chunk
        header_text = headers.decode('utf-8')
        if "200 OK" not in header_text:
            print(f"[HTTP] 响应错误: {header_text[:100]}")
            sock.close()
            return False
        if "transfer-encoding: chunked" not in header_text.lower():
            print("[HTTP] 不支持非chunked编码")
            sock.close()
            return False
    except Exception as e:
        print(f"[HTTP] 头部解析失败: {e}")
        sock.close()
        return False

    # 5. 启动双线程
    print("[主线程] 启动生产者线程（接收数据）")
    _thread.start_new_thread(producer_thread, (sock,))  # 传入已建立的sock
    print("[主线程] 启动消费者线程（播放音频）")
    _thread.start_new_thread(consumer_thread, ())

    # 6. 主线程等待结束
    while not PLAY_FINISH_FLAG or len(AUDIO_QUEUE) > 0:
        if ERROR_FLAG:
            print("[主线程] 检测到错误，终止任务")
            PLAY_FINISH_FLAG = True
        time.sleep(0.1)

    # 7. 清理资源
    sock.close()
    print("[主线程] 所有任务结束")
    return not ERROR_FLAG

# ===================== 主程序 =====================
def main():
    print("\n" + "=" * 60)
    print("ESP32 TTS 双线程流式播放程序（解决卡顿）")
    print("=" * 60)
    # 导入ssl模块（放在main里，避免初始化顺序问题）
    global ssl
    import ssl

    success = tts_api_request(TEXT)
    if success:
        print("\n✅ 播放成功")
    else:
        print("\n❌ 播放失败")

if __name__ == "__main__":
    main()
