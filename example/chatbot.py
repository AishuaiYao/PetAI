import socket
import json
import time
import network
import ubinascii
import _thread
from machine import I2S, Pin

WIFI_SSID = "CMCC-huahua"
WIFI_PASSWORD = "*HUAHUAshi1zhimao"
API_KEY = 'sk-943f95da67d04893b70c02be400e2935' #不要使用2935
COLLECT_SECONDS = 5
SAMPLE_RATE = 16000
RECV_BUFFER_SIZE = 8192
vad_threshold = 500
VAD_INITIALIZATION_SECONDS = 2
SILENCE_FRAMES = 10
VOICE_FRAMES = 10

VOICE = "Cherry"
LANGUAGE = "Chinese"

API_HOST = "dashscope.aliyuncs.com"
API_PATH_TTS = "/api/v1/services/aigc/multimodal-generation/generation"
API_PATH_ASR = "/api/v1/services/aigc/multimodal-generation/generation"
API_PATH_QWEN = "/compatible-mode/v1/chat/completions"

# I2S音频输出配置
I2S_SCK_PIN = 9
I2S_WS_PIN = 10
I2S_SD_PIN = 8
AMP_ENABLE_PIN = 21
TTS_SAMPLE_RATE = 24000
TTS_BITS = 16
TTS_CHANNELS = 1

# ===================== 共享变量 =====================
audio_buffer = []  # 音频数据缓冲区
buffer_lock = _thread.allocate_lock()  # 保护buffer的锁
tts_receiving_complete = False  # 标记TTS接收线程是否已完成所有工作


def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected():
        print(f"[WiFi] 已连接，IP: {wlan.ifconfig()[0]}")
        return True
    print(f"[WiFi] 正在连接: {WIFI_SSID}")
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)
    for i in range(30):
        if wlan.isconnected():
            print(f"[WiFi] 连接成功，IP: {wlan.ifconfig()[0]}")
            return True
        time.sleep(0.5)
    print("[WiFi] 连接失败")
    return False


def init_microphone():
    """初始化麦克风并丢弃初始化噪音"""
    print("[Mic] 初始化麦克风...")
    mic = I2S(0, sck=Pin(12), ws=Pin(13), sd=Pin(14),
              mode=I2S.RX, bits=32, format=I2S.MONO,
              rate=SAMPLE_RATE, ibuf=48000)

    # 丢弃初始化噪音 - 100ms
    chunk_size = 3200
    discard_chunks = int(16000 * 2 / (chunk_size / 4))
    print(f"[Mic] 丢弃初始化噪音: {discard_chunks}个chunk")
    for _ in range(discard_chunks):
        chunk = bytearray(chunk_size)
        mic.readinto(chunk)

    print("[Mic] 麦克风就绪")
    return mic


def calculate_vad_threshold(mic, seconds):
    """采集环境噪音并计算VAD阈值"""
    print(f"[VAD] 开始采集环境噪音，时长: {seconds}秒...")
    chunk_size = 3200
    chunks_per_second = SAMPLE_RATE * 2 / (chunk_size / 4)
    total_chunks = int(chunks_per_second * seconds)

    rms_values = []

    for i in range(total_chunks):
        chunk = bytearray(chunk_size)
        mic.readinto(chunk)

        rms = calculate_rms(chunk)
        rms_values.append(rms)

    avg_rms = sum(rms_values) / len(rms_values)
    max_rms = max(rms_values)
    min_rms = min(rms_values)

    print(f"[VAD] 环境噪音统计: 平均={avg_rms:.2f}, 最大={max_rms:.2f}, 最小={min_rms:.2f}")

    threshold = avg_rms * 1.5
    print(f"[VAD] 设定阈值: {threshold:.2f} (平均值的2倍)")

    return threshold


def calculate_rms(chunk):
    """计算音频块的RMS值（32位转16位）"""
    import struct
    sample_count = len(chunk) // 4
    sum_squares = 0

    for i in range(sample_count):
        sample_32 = struct.unpack('<i', chunk[i * 4:(i + 1) * 4])[0]
        sample_16 = sample_32 >> 16
        sum_squares += sample_16 * sample_16

    rms = (sum_squares / sample_count) ** 0.5
    return rms


def detect_voice_in_chunk(chunk):
    """检测chunk是否有语音，返回 (rms值, 是否有语音)"""
    rms = calculate_rms(chunk)
    has_voice = rms > vad_threshold
    return rms, has_voice


def collect_audio(mic):
    """采集音频数据，mic为已初始化的麦克风实例"""
    print("[ASR] 等待用户说话...")
    chunk_size = 3200
    collected = bytearray()
    silence_count = 0
    pre_buffer = []  # 预缓存，保存最近的10个chunk（5个可能静音 + 5个语音）
    post_buffer = []  # 后缓存，保存录音结束前的静音chunks
    voice_count = 0
    recording = False

    while True:
        chunk = bytearray(chunk_size)
        mic.readinto(chunk)

        rms, has_voice = detect_voice_in_chunk(chunk)

        if not recording:
            pre_buffer.append(chunk)
            if len(pre_buffer) > 10:
                pre_buffer.pop(0)

            if has_voice:
                voice_count += 1
                print(f"[VAD] 检测到语音: 能量={rms:.2f}, 阈值={vad_threshold:.2f}")
            else:
                voice_count = 0
                print(f"[VAD] 检测到静音: 能量={rms:.2f}, 阈值={vad_threshold:.2f}")

            if voice_count >= VOICE_FRAMES:
                print("[ASR] 检测到说话，开始录音...")
                recording = True
                collected = bytearray()
                for buf in pre_buffer:
                    collected += buf
        else:
            collected += chunk
            if not has_voice:
                silence_count += 1
                post_buffer.append(chunk)
                print(f"[VAD] 检测到静音: 能量={rms:.2f}, 阈值={vad_threshold:.2f} [录音中]")
                if silence_count >= SILENCE_FRAMES:
                    print("[ASR] 检测到静音，录音结束")
                    for buf in post_buffer:
                        collected += buf
                    break
            else:
                silence_count = 0
                post_buffer = []  # 检测到语音时清空post_buffer
                print(f"[VAD] 检测到语音: 能量={rms:.2f}, 阈值={vad_threshold:.2f} [录音中]")

    print(f"[ASR] 采集完成: {len(collected)}字节")
    return collected


def create_wav(audio_data):
    datasize = len(audio_data)
    header = (b"RIFF" + (datasize + 36).to_bytes(4, 'little') + b"WAVE" +
              b"fmt " + b"\x10\x00\x00\x00" + b"\x01\x00" + b"\x01\x00" +
              b"\x80\x3e\x00\x00" + b"\x00\xFA\x00\x00" +
              b"\x04\x00" + b"\x20\x00" + b"data" + datasize.to_bytes(4, 'little'))
    wav = bytearray()
    wav.extend(header)
    wav.extend(audio_data)
    return wav


def asr_api_call(wav_data):
    print("[ASR] 调用API...")
    audio_b64 = ubinascii.b2a_base64(wav_data)[:-1].decode('utf-8')
    json_data = f'''{{"model":"qwen3-asr-flash","input":{{"messages":[{{"role":"user","content":[{{"audio":"data:audio/wav;base64,{audio_b64}"}}]}}]}},"parameters":{{"result_format":"message","language":"zh-CN"}}}}'''

    addr_info = socket.getaddrinfo(API_HOST, 443)[0]
    sock = socket.socket(addr_info[0], addr_info[1], addr_info[2])
    sock.settimeout(30)
    sock.connect(addr_info[-1])

    import ssl
    sock = ssl.wrap_socket(sock, server_hostname=API_HOST)

    request = f"POST {API_PATH_ASR} HTTP/1.1\r\nHost: {API_HOST}\r\nAuthorization: Bearer {API_KEY}\r\nContent-Type: application/json\r\nContent-Length: {len(json_data)}\r\nConnection: close\r\n\r\n"
    sock.write(request.encode('utf-8'))
    sock.write(json_data.encode('utf-8'))

    response = b""
    while True:
        chunk = sock.read(4096)
        if not chunk:
            break
        response += chunk
    sock.close()

    body = response.split(b'\r\n\r\n', 1)[1]
    result = json.loads(body)

    if 'output' not in result:
        print(f"[ASR] 错误响应: {result}")
        return ""

    if 'choices' not in result['output'] or len(result['output']['choices']) == 0:
        print(f"[ASR] 错误响应: {result}")
        return ""

    text = result['output']['choices'][0]['message']['content'][0]['text']
    print(f"[ASR] 识别: {text}")
    return text


def qwen_api_call(text):
    print("[Qwen] 调用API...")
    payload_dict = {"model": "qwen-plus", "messages": [{"role": "system",
                                                        "content": "你是一个ai陪伴机器人，你的名字叫花花，请你和用户对话，每次对话返回的字数不必太多，20字左右就行"},
                                                       {"role": "user", "content": text}]}
    payload_bytes = json.dumps(payload_dict).encode('utf-8')

    addr_info = socket.getaddrinfo(API_HOST, 443)[0]
    sock = socket.socket(addr_info[0], addr_info[1], addr_info[2])
    sock.settimeout(30)
    sock.connect(addr_info[-1])

    import ssl
    sock = ssl.wrap_socket(sock, server_hostname=API_HOST)

    request = f"POST {API_PATH_QWEN} HTTP/1.1\r\nHost: {API_HOST}\r\nAuthorization: Bearer {API_KEY}\r\nContent-Type: application/json\r\nContent-Length: {len(payload_bytes)}\r\nConnection: close\r\n\r\n"
    sock.write(request.encode('utf-8'))
    sock.write(payload_bytes)

    response = b""
    while True:
        chunk = sock.read(4096)
        if not chunk:
            break
        response += chunk
    sock.close()

    body = response.split(b'\r\n\r\n', 1)[1]
    result = json.loads(body)

    if 'choices' not in result or len(result['choices']) == 0:
        print(f"[Qwen] 错误响应: {result}")
        return ""

    content = result['choices'][0]['message']['content']
    print(f"[Qwen] 回复: {content}")
    return content


# ===================== 音频播放线程 =====================
def audio_player():
    """音频播放线程：长期存在，持续从audio_buffer中读取并播放音频数据"""
    print("[TTS] 音频播放线程启动")
    time.sleep(0.5)  # 等待一小段时间确保I2S初始化

    # 初始化I2S音频输出
    Pin(AMP_ENABLE_PIN, Pin.OUT).value(1)  # 启用功放
    audio_out = I2S(
        1,
        sck=Pin(I2S_SCK_PIN),
        ws=Pin(I2S_WS_PIN),
        sd=Pin(I2S_SD_PIN),
        mode=I2S.TX,
        bits=TTS_BITS,
        format=I2S.MONO,
        rate=TTS_SAMPLE_RATE,
        ibuf=48000
    )

    chunk_count = 0

    while True:
        with buffer_lock:
            if audio_buffer:
                # 从缓冲区获取音频数据
                audio_chunk = audio_buffer.pop(0)
            else:
                # 没有数据，继续循环检测
                continue

        # 在锁外播放音频，避免阻塞其他线程
        audio_out.write(audio_chunk)
        chunk_count += 1


# ===================== TTS数据接收与解析 =====================
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


def stream_tts_response(sock):
    """流式处理chunked数据：边接收、边解析、边播放"""
    # 用于缓存未解析完成的SSE行
    sse_buffer = ""
    count = 0
    is_done = False

    print("[HTTP] 开始流式处理chunked数据...")

    while not is_done:
        # 1. 读取chunk大小行
        size_line = b""
        empty_read_count = 0
        max_empty_reads = 20  # 最大连续空读取次数（大约400ms）
        while b'\r\n' not in size_line:
            chunk = sock.read(1)
            if not chunk:
                empty_read_count += 1
                print(f"[HTTP] 中断{empty_read_count}次 {chunk}")
                if empty_read_count > max_empty_reads:
                    print(f"[HTTP] 连续{max_empty_reads}次读取为空，连接可能已断开")
                    return count
                # 短暂等待数据到达
                time.sleep_ms(20)  # 20毫秒，足够网络数据到达
                continue

            empty_read_count = 0
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


def tts_api_call(text):
    """TTS API调用（播放线程已存在，只负责接收数据）"""
    global tts_receiving_complete, audio_buffer

    print(f"[TTS] 开始播放: {text}")

    # 重置状态
    with buffer_lock:
        audio_buffer = []
    tts_receiving_complete = False


    # 建立SSL连接
    addr_info = socket.getaddrinfo(API_HOST, 443)[0]
    sock = socket.socket(addr_info[0], addr_info[1], addr_info[2])
    sock.setsockopt(1, 8, RECV_BUFFER_SIZE)
    sock.settimeout(30)
    sock.connect(addr_info[-1])

    import ssl

    sock = ssl.wrap_socket(sock, server_hostname=API_HOST)
    print("[API] SSL连接建立成功")

    # 构建TTS请求
    payload_dict = {
        "model": "qwen3-tts-flash",
        "input": {"text": text},
        "parameters": {"voice": VOICE, "language_type": LANGUAGE}
    }
    payload_bytes = json.dumps(payload_dict).encode('utf-8')

    # 发送请求
    request_headers = (
        f"POST {API_PATH_TTS} HTTP/1.1\r\n"
        f"Host: {API_HOST}\r\n"
        f"Authorization: Bearer {API_KEY}\r\n"
        f"Content-Type: application/json\r\n"
        f"X-DashScope-SSE: enable\r\n"
        f"Content-Length: {len(payload_bytes)}\r\n"
        f"Connection: close\r\n\r\n"
    )

    sock.write(request_headers.encode('utf-8'))
    sock.write(payload_bytes)
    print(f"[TTS] 请求已发送，文本长度: {len(text)}")

    # 接收HTTP响应头部
    print("[TTS] 接收响应头部...")
    headers = b""
    while b'\r\n\r\n' not in headers:
        chunk = sock.read(1)
        if not chunk:
            print("[TTS] 连接中断")
            sock.close()
            Pin(21, Pin.OUT).value(0)
            return False
        headers += chunk

    header_text = headers.decode('utf-8')
    print(f"[HTTP] 头部接收完成 ({len(headers)} 字节)")

    # 检查HTTP状态码
    if "200 OK" not in header_text:
        print(f"[TTS] 错误响应: {header_text[:100]}")
        sock.close()
        Pin(21, Pin.OUT).value(0)
        return False

    # 流式处理数据（核心修改点）
    total_count = 0
    if "transfer-encoding: chunked" in header_text.lower():
        print("[HTTP] 检测到chunked编码，开始流式处理...")
        # 流式处理chunked数据，边接收边播放
        total_count = stream_tts_response(sock)

    print(f"共接收了 {total_count} 个音频块")

    global  receiving_complete
    with buffer_lock:
        receiving_complete = True
    print("[TTS] 播放完成")

    return True


def main():
    global vad_threshold

    print("===== 语音助手启动 =====")
    if not connect_wifi():
        return

    # 初始化麦克风（只初始化一次，使用I2S(0)）
    mic = init_microphone()

    # 动态计算VAD阈值
    print("\n--- 计算环境噪音阈值 ---")
    print("[VAD] 请保持安静，正在采集环境噪音...")
    vad_threshold = calculate_vad_threshold(mic, VAD_INITIALIZATION_SECONDS)
    print(f"[VAD] 阈值已设定为: {vad_threshold:.2f}")
    print("[VAD] 现在可以开始说话了\n")

    # 启动音频播放线程（长期存在）
    _thread.start_new_thread(audio_player, ())
    time.sleep(0.5)  # 等待播放线程初始化

    while True:
        print("\n--- 新一轮对话 ---")

        # 采集用户语音
        raw_audio = collect_audio(mic)
        wav_data = create_wav(raw_audio)

        # 语音识别
        user_text = asr_api_call(wav_data)

        if user_text:
            # 获取AI回复
            ai_text = qwen_api_call(user_text)
            if ai_text:
                # 语音合成与播放（多线程非阻塞）
                tts_api_call(ai_text)

        time.sleep(1)

    # 程序退出时关闭麦克风
    mic.deinit()
    print("[Mic] 麦克风已关闭")


if __name__ == "__main__":
    main()
