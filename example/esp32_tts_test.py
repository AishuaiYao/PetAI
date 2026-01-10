import socket
import json
import struct
import time
import network

# ===================== 核心配置 =====================
# --- 配置 ---
WIFI_SSID = "CMCC-huahua"
WIFI_PASSWORD = "*HUAHUAshi1zhimao"
API_KEY = 'sk-943f95da67d04893b70c02be400e2935'
TEXT = "测试文本"
VOICE = "Cherry"
LANGUAGE = "Chinese"

# TTS API配置
API_HOST = "dashscope.aliyuncs.com"
API_PORT = 443
API_PATH = "/api/v1/services/aigc/multimodal-generation/generation"


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
    # 检查是否包含output字段
    if "output" not in data:
        return False, "响应缺少'output'字段"

    output = data["output"]

    # 检查finish_reason（注意：API返回的"null"是字符串，表示流继续）
    finish_reason = output.get("finish_reason")
    if finish_reason == "stop":
        return True, "流式传输正常完成"
    elif finish_reason and finish_reason != "null":
        return False, f"流提前结束，原因: {finish_reason}"

    # 检查audio数据
    audio_info = output.get("audio", {})
    if "data" in audio_info:
        audio_data = audio_info["data"]
        # 检查是否为base64格式（非空字符串即为有效）
        if isinstance(audio_data, str) and len(audio_data) > 0:
            return True, f"音频数据正常，长度: {len(audio_data)}"
        else:
            # 空字符串也认为是正常的（可能是间隔包）
            return True, "音频数据为空（间隔包）"
    else:
        # 如果没有audio数据但有其他字段，也算正常
        return True, "响应包含音频相关字段"

    return False, "未知响应格式"


# ===================== TTS API请求（仅获取返回） =====================
def tts_api_request(text):
    """
    核心函数：请求TTS API并验证返回结果（不播放音频）
    返回: (success: bool, total_audio_chunks: int, validation_results: list)
    """
    # 1. WiFi连接检查
    if not connect_wifi():
        return False, 0, []

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
        print(f"[DEBUG] 发送的payload: {payload}")

        request_headers = (
            f"POST {API_PATH} HTTP/1.1\r\n"
            f"Host: {API_HOST}\r\n"
            f"Authorization: Bearer {API_KEY}\r\n"
            f"Content-Type: application/json\r\n"
            f"X-DashScope-SSE: enable\r\n"
            f"Content-Length: {len(payload)}\r\n"
            f"Connection: close\r\n\r\n"
        )

        # 4. 发送请求
        payload_bytes = payload.encode('utf-8')
        print(f"[DEBUG] payload字节长度: {len(payload_bytes)}")
        print(f"[DEBUG] payload字节内容(前100): {payload_bytes[:100]}")

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
                line = line.strip()

                # 打印调试信息：非空行
                if line and not line.startswith(b'data:'):
                    print(f"[DEBUG] 收到非SSE行: {line[:100]}")

                if not line or not line.startswith(b'data:'):
                    continue

                # 解析SSE数据行
                sse_data = line[5:].strip()
                print(f"[DEBUG] SSE数据长度: {len(sse_data)}")
                if sse_data == b'[DONE]':
                    print("[API] 收到流结束标记")
                    break

                # 解析JSON并校验
                try:
                    data_str = sse_data.decode('utf-8')
                    print(f"[DEBUG] 尝试解析JSON: {data_str[:200]}")
                    data = json.loads(data_str)

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

                        # 统计音频块数量
                        audio_info = output.get("audio", {})
                        if "data" in audio_info:
                            audio_chunks += 1
                            print(f"[API] 收到音频块 #{audio_chunks}")

                except Exception as e:
                    error_msg = f"解析失败: {e}"
                    validation_results.append({
                        "valid": False,
                        "message": error_msg,
                        "data_preview": sse_data[:50] if sse_data else "empty"
                    })
                    print(f"[校验] ✗ {error_msg}")
                    continue

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
    print("ESP32 TTS API 校验程序")
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

