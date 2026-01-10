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


# ===================== 调试保存函数 =====================
def save_sse_data(sse_data, prefix):
    """保存SSE数据到文件，用于调试"""
    global SSE_SAVE_COUNT
    if not DEBUG_SAVE_SSE:
        return

    SSE_SAVE_COUNT += 1
    try:
        filename = f"sse_debug_{SSE_SAVE_COUNT}_{prefix}.txt"
        with open(filename, "wb") as f:
            f.write(sse_data)
        print(f"[DEBUG] 已保存: {filename}, 大小: {len(sse_data)}")
    except Exception as e:
        print(f"[DEBUG] 保存失败: {e}")


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
    from machine import I2S, Pin
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


# ===================== 响应校验函数 =====================
def validate_response(data):
    """
    校验TTS API返回的数据是否正常
    返回: (is_valid: bool, error_msg: str)
    """
    try:
        # 检查是否包含output字段
        if "output" not in data:
            return False, "响应缺少'output'字段"

        output = data["output"]

        # 检查finish_reason（注意：API返回的"null"可能是字符串、整数或None，表示流继续）
        finish_reason = output.get("finish_reason")

        # 转换为字符串处理
        if finish_reason is None:
            return True, "流继续中"

        finish_reason_str = str(finish_reason)
        if finish_reason_str == "stop" or finish_reason_str == "1":
            return True, "流式传输正常完成"
        elif finish_reason_str and finish_reason_str not in ["null", "0", "None"]:
            return False, "流提前结束，原因: " + finish_reason_str

        # 检查audio数据
        audio_info = output.get("audio", {})
        if "data" in audio_info:
            audio_data = audio_info["data"]
            # 检查是否为base64格式（非空字符串即为有效）
            if isinstance(audio_data, str) and len(audio_data) > 0:
                return True, "音频数据正常，长度: " + str(len(audio_data))
            else:
                # 空字符串也认为是正常的（可能是间隔包）
                return True, "音频数据为空（间隔包）"
        else:
            # 如果没有audio数据但有其他字段，也算正常
            return True, "响应包含音频相关字段"

        return False, "未知响应格式"
    except Exception as e:
        return False, "校验异常: " + str(e)


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

    try:
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

        # 5. 接收并解析流式响应
        response_buffer = b""
        stream_continue = True
        headers_parsed = False  # 标记HTTP响应头是否已解析
        sse_accumulator = b""  # 累积SSE数据（处理长JSON被分包的情况）

        while stream_continue:
            try:
                chunk = sock.read(1024)
            except OSError as e:
                if "timeout" in str(e).lower():
                    print("[API] 读取数据超时")
                    break
                else:
                    raise e

            if not chunk:
                break
            response_received = True

            response_buffer += chunk

            # 跳过HTTP响应头（找到空行后才开始解析SSE）
            if not headers_parsed:
                if b"\r\n\r\n" in response_buffer:
                    # 找到响应头结束位置
                    headers_end = response_buffer.index(b"\r\n\r\n") + 4
                    headers = response_buffer[:headers_end].decode('utf-8', 'ignore')
                    response_buffer = response_buffer[headers_end:]
                    headers_parsed = True

                    # 检查HTTP状态码
                    first_line = headers.split('\r\n')[0]
                    print(f"[API] HTTP响应: {first_line}")
                    if "200" not in first_line:
                        print(f"[API] HTTP错误响应:\n{headers[:500]}")
                        break
                else:
                    # 继续读取直到收到完整响应头
                    continue

            # 按行解析SSE
            while b"\n" in response_buffer and stream_continue:
                line, response_buffer = response_buffer.split(b"\n", 1)
                line_stripped = line.strip()

                # 空行表示一个SSE事件的结束，尝试解析累积的数据
                if not line_stripped:
                    if sse_accumulator:
                        # 解析累积的数据
                        sse_data = sse_accumulator
                        sse_accumulator = b""

                        if sse_data == b'[DONE]':
                            print("[API] 收到流结束标记")
                            break

                        # 跳过过短的数据（不完整的数据）
                        if len(sse_data) < 50:
                            sse_accumulator = b""
                            continue

                        # 保存调试数据
                        save_sse_data(sse_data, "empty_line")

                        # 解析JSON并校验
                        try:
                            data_str = sse_data.decode('utf-8')
                            data = json.loads(data_str)

                            # 保存成功解析的JSON
                            save_sse_data(json.dumps(data).encode('utf-8'), f"success_{SSE_SAVE_COUNT}")

                            # 调用校验函数
                            is_valid, error_msg = validate_response(data)
                            validation_results.append({
                                "valid": is_valid,
                                "message": error_msg,
                                "data_keys": list(data.keys())
                            })

                            print(f"[校验] 结果: {'✓' if is_valid else '✗'} | {error_msg}")

                            # 检查流结束
                            if "output" in data:
                                output = data["output"]
                                if output.get("finish_reason") == "stop":
                                    print("[API] 流式传输完成")
                                    stream_continue = False
                                    break

                                # 解码并播放音频
                                audio_info = output.get("audio", {})
                                if "data" in audio_info:
                                    audio_base64 = audio_info["data"]
                                    if audio_base64:  # 非空音频数据
                                        audio_chunks += 1
                                        print(f"[API] 收到音频块 #{audio_chunks}")

                                        # Base64解码
                                        audio_bytes = base64_decode(audio_base64.encode('utf-8'))
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

                        except Exception as e:
                            error_msg = f"解析失败: {e}"
                            validation_results.append({
                                "valid": False,
                                "message": error_msg,
                                "data_preview": sse_data[:100] if sse_data else "empty"
                            })
                            print(f"[校验] ✗ {error_msg}")
                            print(f"[DEBUG] 失败数据长度: {len(sse_data)}, 内容: {sse_data[:200] if sse_data else 'empty'}")
                            continue

                # 处理以 'data:' 开头的行
                if line_stripped.startswith(b'data:'):
                    data_content = line_stripped[5:].strip()

                    # 检查是否是结束标记
                    if data_content == b'[DONE]':
                        print("[API] 收到流结束标记")
                        stream_continue = False
                        break

                    # 如果累积器不为空，说明遇到了新事件，先解析之前的数据
                    if sse_accumulator and len(sse_accumulator) >= 50:
                        # 尝试解析之前累积的数据
                        sse_data = sse_accumulator
                        sse_accumulator = b""

                        # 保存调试数据
                        save_sse_data(sse_data, "new_data")

                        try:
                            data_str = sse_data.decode('utf-8')
                            data = json.loads(data_str)

                            # 保存成功解析的JSON
                            save_sse_data(json.dumps(data).encode('utf-8'), f"success_{SSE_SAVE_COUNT}")

                            # 调用校验函数
                            is_valid, error_msg = validate_response(data)
                            validation_results.append({
                                "valid": is_valid,
                                "message": error_msg,
                                "data_keys": list(data.keys())
                            })

                            print(f"[校验] 结果: {'✓' if is_valid else '✗'} | {error_msg}")

                            # 检查流结束
                            if "output" in data:
                                output = data["output"]
                                if output.get("finish_reason") == "stop":
                                    print("[API] 流式传输完成")
                                    stream_continue = False
                                    break

                                # 解码并播放音频
                                audio_info = output.get("audio", {})
                                if "data" in audio_info:
                                    audio_base64 = audio_info["data"]
                                    if audio_base64:  # 非空音频数据
                                        audio_chunks += 1
                                        print(f"[API] 收到音频块 #{audio_chunks}")

                                        # Base64解码
                                        audio_bytes = base64_decode(audio_base64.encode('utf-8'))
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

                        except Exception as e:
                            # 解析失败，保存失败的数据
                            save_sse_data(sse_data, "failed_parse")

                            error_msg = f"解析失败: {e}"
                            validation_results.append({
                                "valid": False,
                                "message": error_msg,
                                "data_preview": sse_data[:100] if sse_data else "empty"
                            })
                            print(f"[校验] ✗ {error_msg}")
                            print(f"[DEBUG] 失败数据长度: {len(sse_data)}, 内容: {sse_data[:200] if sse_data else 'empty'}")

                    # 累积新数据
                    if data_content:
                        sse_accumulator += data_content

                # 跳过其他SSE元数据行（id, event等）

        return True, audio_chunks, validation_results

    except Exception as e:
        print(f"[API] 执行异常: {e}")
        import sys
        sys.print_exception(e)
        return False, audio_chunks, validation_results

    finally:
        # 资源清理
        try:
            if sock:
                sock.close()
        except:
            pass
        deinit_audio(i2s, amp_pin)
        print("[API] 连接已关闭")


# ===================== 打印校验报告 =====================
def print_validation_report(audio_chunks, validation_results):
    """打印详细的校验报告"""
    print("\n" + "=" * 50)
    print("校验报告")
    print("=" * 50)

    # 统计
    total = len(validation_results)
    valid_count = sum(1 for r in validation_results if r["valid"])
    invalid_count = total - valid_count

    print(f"总共收到的数据块: {total}")
    print(f"音频块数量: {audio_chunks}")
    print(f"校验通过: {valid_count}")
    print(f"校验失败: {invalid_count}")

    if invalid_count > 0:
        print("\n失败的校验项:")
        for i, r in enumerate(validation_results, 1):
            if not r["valid"]:
                print(f"  #{i}: {r.get('message', 'Unknown')}")

    print("=" * 50)


# ===================== 主程序 =====================
def main():
    """主程序入口"""
    print("\n" + "=" * 50)
    print("ESP32 TTS 流式播放程序")
    print("=" * 50)

    success, audio_chunks, validation_results = tts_api_request(TEXT)

    if success:
        print("\n[结果] API请求成功完成")
        print_validation_report(audio_chunks, validation_results)

        # 最终判断
        all_valid = all(r["valid"] for r in validation_results)
        if all_valid and audio_chunks > 0:
            print("\n✅ 所有校验通过！API返回正常")
        else:
            print("\n⚠️ 部分校验未通过，请查看上方报告")
    else:
        print("\n❌ API请求失败")


if __name__ == "__main__":
    main()


