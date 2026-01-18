import socket
import json
import time
import network
import ubinascii
from machine import I2S, Pin

WIFI_SSID = "CMCC-huahua"
WIFI_PASSWORD = "*HUAHUAshi1zhimao"
API_KEY = 'sk-943f95da67d04893b70c02be400e2935'
COLLECT_SECONDS = 5
SAMPLE_RATE = 16000
RECV_BUFFER_SIZE = 8192
VAD_THRESHOLD = 3000
SILENCE_FRAMES = 200

VOICE = "Cherry"
LANGUAGE = "Chinese"

API_HOST = "dashscope.aliyuncs.com"


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
              rate=SAMPLE_RATE, ibuf=40000)

    # 丢弃初始化噪音 - 100ms
    chunk_size = 3200
    discard_chunks = int(16000 * 0.1 / (chunk_size / 4))
    print(f"[Mic] 丢弃初始化噪音: {discard_chunks}个chunk")
    for _ in range(discard_chunks):
        chunk = bytearray(chunk_size)
        mic.readinto(chunk)

    print("[Mic] 麦克风就绪")
    return mic


def detect_voice_in_chunk(chunk):
    """检测chunk是否有语音（32位转16位）"""
    import struct
    sample_count = len(chunk) // 4
    sum_squares = 0

    for i in range(sample_count):
        sample_32 = struct.unpack('<i', chunk[i * 4:(i + 1) * 4])[0]
        sample_16 = sample_32 >> 16
        sum_squares += sample_16 * sample_16

    rms = (sum_squares / sample_count) ** 0.5
    print(rms)
    return rms > VAD_THRESHOLD


def collect_audio(mic):
    """采集音频数据，mic为已初始化的麦克风实例"""
    print("[ASR] 等待用户说话...")
    chunk_size = 3200
    collected = bytearray()
    silence_count = 0
    recording = False

    try:
        while True:
            chunk = bytearray(chunk_size)
            mic.readinto(chunk)

            has_voice = detect_voice_in_chunk(chunk)

            if not recording:
                if has_voice:
                    print("[ASR] 检测到说话，开始录音...")
                    recording = True
                    collected += chunk
            else:
                collected += chunk

                if not has_voice:
                    silence_count += 1
                    if silence_count >= SILENCE_FRAMES:
                        print("[ASR] 检测到静音，录音结束")
                        break
                else:
                    silence_count = 0

    finally:
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

    request = f"POST /api/v1/services/aigc/multimodal-generation/generation HTTP/1.1\r\nHost: {API_HOST}\r\nAuthorization: Bearer {API_KEY}\r\nContent-Type: application/json\r\nContent-Length: {len(json_data)}\r\nConnection: close\r\n\r\n"
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
    text = result['output']['choices'][0]['message']['content'][0]['text']
    print(f"[ASR] 识别: {text}")
    return text


def qwen_api_call(text):
    print("[Qwen] 调用API...")
    payload_dict = {"model": "qwen-plus", "messages": [{"role": "system", "content": "You are a helpful assistant."},
                                                       {"role": "user", "content": text}]}
    payload_bytes = json.dumps(payload_dict).encode('utf-8')

    addr_info = socket.getaddrinfo(API_HOST, 443)[0]
    sock = socket.socket(addr_info[0], addr_info[1], addr_info[2])
    sock.settimeout(30)
    sock.connect(addr_info[-1])

    import ssl
    sock = ssl.wrap_socket(sock, server_hostname=API_HOST)

    request = f"POST /compatible-mode/v1/chat/completions HTTP/1.1\r\nHost: {API_HOST}\r\nAuthorization: Bearer {API_KEY}\r\nContent-Type: application/json\r\nContent-Length: {len(payload_bytes)}\r\nConnection: close\r\n\r\n"
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
    content = result['choices'][0]['message']['content']
    print(f"[Qwen] 回复: {content}")
    return content


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


def tts_api_call(text):
    print(f"[TTS] 播放: {text}")
    Pin(21, Pin.OUT).value(1)
    i2s = I2S(0, sck=Pin(9), ws=Pin(10), sd=Pin(8), mode=I2S.TX, bits=16, format=I2S.MONO, rate=24000, ibuf=24000)

    payload_dict = {"model": "qwen3-tts-flash", "input": {"text": text},
                    "parameters": {"voice": VOICE, "language_type": LANGUAGE}}
    payload = json.dumps(payload_dict).encode('utf-8')

    addr_info = socket.getaddrinfo(API_HOST, 443)[0]
    sock = socket.socket(addr_info[0], addr_info[1], addr_info[2])
    sock.setsockopt(1, 8, RECV_BUFFER_SIZE)
    sock.settimeout(15)
    sock.connect(addr_info[-1])

    import ssl
    sock = ssl.wrap_socket(sock, server_hostname=API_HOST)

    request = f"POST /api/v1/services/aigc/multimodal-generation/generation HTTP/1.1\r\nHost: {API_HOST}\r\nAuthorization: Bearer {API_KEY}\r\nContent-Type: application/json\r\nX-DashScope-SSE: enable\r\nContent-Length: {len(payload)}\r\nConnection: close\r\n\r\n"
    sock.write(request.encode('utf-8'))
    sock.write(payload)

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
            if parsed["type"] == "done":
                break
            audio_data, is_done = handle_chunk_data(parsed["data"])
            if audio_data:
                audio_bytes = ubinascii.a2b_base64(audio_data)
                i2s.write(audio_bytes)
            if is_done:
                break
    sock.close()
    i2s.deinit()
    print("[TTS] 播放完成")


def main():
    print("===== 语音助手启动 =====")
    if not connect_wifi():
        return

    # 初始化麦克风（只初始化一次）
    mic = init_microphone()

    try:
        while True:
            print("\n--- 新一轮对话 ---")
            raw_audio = collect_audio(mic)
            wav_data = create_wav(raw_audio)
            user_text = asr_api_call(wav_data)

            if user_text:
                ai_text = qwen_api_call(user_text)
                if ai_text:
                    tts_api_call(ai_text)

            time.sleep(1)
    finally:
        # 程序退出时关闭麦克风
        mic.deinit()
        print("[Mic] 麦克风已关闭")


if __name__ == "__main__":
    main()
