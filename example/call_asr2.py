import time
import ujson as json
import urequests as requests
import ubinascii
from machine import I2S, Pin
import network
import socket
import gc

# --- 配置 ---
WIFI_SSID = "CMCC-huahua"
WIFI_PASSWORD = "*HUAHUAshi1zhimao"
API_KEY = 'sk-943f95da67d04893b70c02be400e2935'
MODEL_NAME = "qwen3-asr-flash"
API_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"

SAMPLE_RATE = 16000
COLLECT_SECONDS = 2  # 采集5秒

# 引脚
mic = I2S(0, sck=Pin(12), ws=Pin(13), sd=Pin(14),
          mode=I2S.RX, bits=32, format=I2S.MONO,
          rate=SAMPLE_RATE, ibuf=40000)


# --- 网络延迟检测函数 ---
def measure_network_latency():
    """全面测量网络延迟"""
    print(f"\n[{time.time():.3f}] === 开始网络延迟检测 ===")

    test_servers = [
        ("DNS服务器", "8.8.8.8", 53),  # Google DNS
        ("阿里云DNS", "223.5.5.5", 53),  # 阿里云DNS
        ("百度", "www.baidu.com", 80),
        ("阿里云API", "dashscope.aliyuncs.com", 443),
    ]

    gc.collect()  # 垃圾回收，确保内存干净

    for server_name, host, port in test_servers:
        print(f"\n[{time.time():.3f}] 测试 {server_name} ({host}:{port})...")

        try:
            # 1. DNS解析延迟（如果是域名）
            if not host.replace('.', '').isdigit():  # 如果是域名而不是IP
                dns_start = time.time()
                try:
                    addr_info = socket.getaddrinfo(host, port)
                    dns_end = time.time()
                    ip_address = addr_info[0][4][0]
                    print(f"[{time.time():.3f}]   DNS解析: {dns_end - dns_start:.3f}秒 -> {ip_address}")
                    host = ip_address  # 使用解析后的IP进行ping测试
                except Exception as e:
                    print(f"[{time.time():.3f}]   ❌ DNS解析失败: {e}")
                    continue

            # 2. TCP连接延迟（类似ping）
            ping_results = []
            for i in range(3):  # ping 3次
                try:
                    sock = socket.socket()
                    sock.settimeout(3)  # 3秒超时

                    connect_start = time.time()
                    sock.connect((host, port))
                    connect_end = time.time()

                    latency = (connect_end - connect_start) * 1000  # 转换为毫秒
                    ping_results.append(latency)

                    sock.close()

                    print(f"[{time.time():.3f}]   Ping {i + 1}: {latency:.1f}ms")
                    time.sleep(0.5)  # 间隔0.5秒

                except Exception as e:
                    print(f"[{time.time():.3f}]   Ping {i + 1}失败: {e}")
                    break
                finally:
                    if 'sock' in locals():
                        try:
                            sock.close()
                        except:
                            pass

            # 3. 计算统计
            if ping_results:
                avg_latency = sum(ping_results) / len(ping_results)
                min_latency = min(ping_results)
                max_latency = max(ping_results)
                jitter = max_latency - min_latency  # 抖动

                print(f"[{time.time():.3f}]   📊 统计:")
                print(f"[{time.time():.3f}]     平均延迟: {avg_latency:.1f}ms")
                print(f"[{time.time():.3f}]     最小延迟: {min_latency:.1f}ms")
                print(f"[{time.time():.3f}]     最大延迟: {max_latency:.1f}ms")
                print(f"[{time.time():.3f}]     抖动: {jitter:.1f}ms")

                # 延迟评级
                if avg_latency < 50:
                    rating = "优秀 🚀"
                elif avg_latency < 100:
                    rating = "良好 👍"
                elif avg_latency < 200:
                    rating = "一般 ⚠️"
                elif avg_latency < 500:
                    rating = "较差 🐌"
                else:
                    rating = "很差 ❌"

                print(f"[{time.time():.3f}]     评级: {rating}")

            # 4. 针对API服务器的额外测试
            if server_name == "阿里云API":
                print(f"\n[{time.time():.3f}]   执行API服务器额外测试...")

                # 测试HTTPS连接建立时间
                try:
                    sock = socket.socket()
                    sock.settimeout(5)

                    # TCP握手时间
                    tcp_start = time.time()
                    sock.connect((host, port))
                    tcp_end = time.time()

                    # TLS握手模拟（发送HTTPS请求头）
                    ssl_start = time.time()
                    sock.send(b"GET / HTTP/1.1\r\nHost: dashscope.aliyuncs.com\r\n\r\n")

                    # 读取一点响应来判断连接是否正常
                    sock.settimeout(2)
                    try:
                        response = sock.recv(100)
                    except:
                        response = b""

                    ssl_end = time.time()

                    print(f"[{time.time():.3f}]     TCP握手: {(tcp_end - tcp_start) * 1000:.1f}ms")
                    print(f"[{time.time():.3f}]     SSL/TLS握手: {(ssl_end - ssl_start) * 1000:.1f}ms")
                    print(f"[{time.time():.3f}]     总连接建立: {(ssl_end - tcp_start) * 1000:.1f}ms")

                    if b"HTTP" in response or b"TLS" in response or b"SSL" in response:
                        print(f"[{time.time():.3f}]     服务器响应: 正常")
                    else:
                        print(f"[{time.time():.3f}]     服务器响应: 异常或无响应")

                    sock.close()

                except Exception as e:
                    print(f"[{time.time():.3f}]     API服务器测试失败: {e}")

        except Exception as e:
            print(f"[{time.time():.3f}]   ❌ {server_name}测试失败: {e}")

        time.sleep(1)  # 测试间隔

    print(f"\n[{time.time():.3f}] === 网络延迟检测完成 ===")
    gc.collect()


# --- 网络速度测试函数 ---
def measure_network_speed():
    """简单网络速度测试"""
    print(f"\n[{time.time():.3f}] === 开始网络速度测试 ===")

    test_urls = [
        ("小型测试", "http://httpbin.org/bytes/1024"),  # 1KB
        ("中型测试", "http://httpbin.org/bytes/10240"),  # 10KB
    ]

    for test_name, url in test_urls:
        print(f"\n[{time.time():.3f}] {test_name} ({url})...")

        try:
            # 先解析域名
            domain = url.split('/')[2]
            dns_start = time.time()
            addr_info = socket.getaddrinfo(domain, 80)
            dns_time = time.time() - dns_start

            start_time = time.time()
            response = requests.get(url, timeout=10)
            end_time = time.time()

            if response.status_code == 200:
                data_size = len(response.content)
                total_time = end_time - start_time
                speed_kbps = (data_size * 8) / total_time / 1024  # Kbps
                speed_mbps = speed_kbps / 1024  # Mbps

                print(f"[{time.time():.3f}]   ✅ 下载成功")
                print(f"[{time.time():.3f}]   数据大小: {data_size} 字节")
                print(f"[{time.time():.3f}]   DNS时间: {dns_time:.3f}秒")
                print(f"[{time.time():.3f}]   下载时间: {total_time:.3f}秒")
                print(f"[{time.time():.3f}]   下载速度: {speed_kbps:.2f} Kbps ({speed_mbps:.2f} Mbps)")

                # 速度评级
                if speed_mbps > 10:
                    rating = "极快 🚀"
                elif speed_mbps > 5:
                    rating = "快速 ⚡"
                elif speed_mbps > 2:
                    rating = "一般 👍"
                elif speed_mbps > 0.5:
                    rating = "较慢 🐌"
                else:
                    rating = "很慢 ❌"

                print(f"[{time.time():.3f}]   评级: {rating}")

            else:
                print(f"[{time.time():.3f}]   ❌ 下载失败: {response.status_code}")

        except Exception as e:
            print(f"[{time.time():.3f}]   ❌ {test_name}测试失败: {e}")

        time.sleep(2)

    print(f"\n[{time.time():.3f}] === 网络速度测试完成 ===")


# --- 网络状态检查函数 ---
def check_network_status():
    """检查网络状态，包括AP模式和WiFi连接"""
    start_time = time.time()
    print(f"\n[{start_time:.3f}] === 网络状态检查 ===")

    # 检查AP模式
    ap = network.WLAN(network.AP_IF)
    ap_active = ap.active()
    print(f"[{time.time():.3f}] AP模式状态: {'开启' if ap_active else '关闭'}")
    if ap_active:
        print(f"[{time.time():.3f}] ⚠️ 警告: AP模式已开启，建议关闭以节省资源")
        ap.active(False)
        print(f"[{time.time():.3f}] 已关闭AP模式")

    # 检查STA模式
    sta = network.WLAN(network.STA_IF)
    sta_active = sta.active()
    print(f"[{time.time():.3f}] STA模式状态: {'开启' if sta_active else '关闭'}")

    if sta.isconnected():
        print(f"[{time.time():.3f}] WiFi连接状态: 已连接")
        config = sta.ifconfig()
        print(f"[{time.time():.3f}] IP地址: {config[0]}")
        print(f"[{time.time():.3f}] 子网掩码: {config[1]}")
        print(f"[{time.time():.3f}] 网关: {config[2]}")
        print(f"[{time.time():.3f}] DNS: {config[3]}")

        # 信号强度
        try:
            # 不同版本的MicroPython获取信号强度的方法不同
            if hasattr(sta, 'status'):
                # 尝试获取RSSI
                try:
                    rssi = sta.status('rssi')
                    print(f"[{time.time():.3f}] 信号强度: {rssi} dBm")

                    # 信号质量评级
                    if rssi >= -50:
                        quality = "优秀 📶📶📶"
                    elif rssi >= -60:
                        quality = "良好 📶📶"
                    elif rssi >= -70:
                        quality = "一般 📶"
                    elif rssi >= -80:
                        quality = "较差 📡"
                    else:
                        quality = "很差 ❌"

                    print(f"[{time.time():.3f}] 信号质量: {quality}")
                except:
                    # 如果status方法不支持参数
                    status_info = sta.status()
                    print(f"[{time.time():.3f}] 连接状态: {status_info}")
        except Exception as e:
            print(f"[{time.time():.3f}] 信号强度: 无法获取 ({e})")
    else:
        print(f"[{time.time():.3f}] WiFi连接状态: 未连接")

    end_time = time.time()
    print(f"[{end_time:.3f}] 网络检查总耗时: {end_time - start_time:.3f}秒")
    print(f"[{end_time:.3f}] === 网络检查结束 ===\n")

    return sta.isconnected()


# --- 核心函数 ---
def connect_wifi():
    start_time = time.time()
    print(f"[{start_time:.3f}] 开始连接Wi-Fi...")

    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    # 先检查是否已连接
    if wlan.isconnected():
        end_time = time.time()
        print(f"[{end_time:.3f}] ✅ 已连接Wi-Fi，IP: {wlan.ifconfig()[0]}")
        return True

    # 连接Wi-Fi
    connect_start = time.time()
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)
    print(f"[{time.time():.3f}]   正在连接到 {WIFI_SSID}...")

    for i in range(30):  # 增加到30次尝试
        if wlan.isconnected():
            connect_end = time.time()
            end_time = time.time()
            print(f"[{end_time:.3f}] ✅ Wi-Fi连接成功")
            print(f"[{end_time:.3f}]   连接耗时: {connect_end - connect_start:.2f}秒")
            print(f"[{end_time:.3f}]   IP地址: {wlan.ifconfig()[0]}")

            return True

        # 显示连接状态
        status = wlan.status()
        if i % 5 == 0:  # 每5次打印一次状态
            status_map = {
                1000: "未连接",
                1001: "连接中",
                1010: "已连接",
                202: "密码错误",
                201: "未找到AP",
            }
            status_text = status_map.get(status, f"未知({status})")
            print(f"[{time.time():.3f}]   连接状态: {status_text} (尝试 {i + 1}/30)")

        time.sleep(0.5)

    end_time = time.time()
    print(f"[{end_time:.3f}] ❌ Wi-Fi连接失败，总耗时: {end_time - start_time:.2f}秒")
    return False


def collect_5s_audio():
    """采集5秒音频（441模块格式）"""
    start_time = time.time()
    print(f"[{start_time:.3f}] 🎤 开始采集{COLLECT_SECONDS}秒音频...")

    # 计算需要的数据量：5秒 × 16000样本/秒 × 4字节/样本
    total_bytes = COLLECT_SECONDS * SAMPLE_RATE * 4
    chunk_size = 3200  # 每次读0.05秒数据
    collected = bytearray()

    progress_start = time.time()
    while len(collected) < total_bytes:
        chunk = bytearray(chunk_size)
        chunk_start = time.time()
        mic.readinto(chunk)
        collected.extend(chunk)

        # 显示进度
        progress = len(collected) / total_bytes * 100
        if time.time() - progress_start >= 1:
            current_time = time.time()
            print(f"[{current_time:.3f}]   进度: {progress:.0f}%")
            progress_start = time.time()

    end_time = time.time()
    print(f"[{end_time:.3f}] ✅ 采集完成: {len(collected)} 字节，耗时: {end_time - start_time:.2f}秒")
    return collected


def create_wav_441(audio_data):
    """为441模块音频创建WAV"""
    start_time = time.time()
    print(f"[{start_time:.3f}] 🎵 开始创建WAV文件...")

    # WAV头 (32位, 16000Hz, 单声道)
    datasize = len(audio_data)
    header = (
            b"RIFF" + (datasize + 36).to_bytes(4, 'little') + b"WAVE" +
            b"fmt " + b"\x10\x00\x00\x00" + b"\x01\x00" +  # PCM格式
            b"\x01\x00" +  # 单声道
            b"\x80\x3e\x00\x00" +  # 16000Hz
            b"\x00\xFA\x00\x00" +  # 字节率 = 16000*4 = 64000
            b"\x04\x00" +  # 块对齐 = 4字节
            b"\x20\x00" +  # 32位
            b"data" + datasize.to_bytes(4, 'little')
    )

    wav = bytearray()
    wav.extend(header)
    wav.extend(audio_data)

    end_time = time.time()
    print(f"[{end_time:.3f}] ✅ WAV文件创建完成，大小: {len(wav)} 字节，耗时: {end_time - start_time:.2f}秒")
    return wav


def call_api_with_detailed_timing(wav_data):
    """调用API，包含详细的耗时分析"""
    total_start = time.time()
    print(f"\n[{total_start:.3f}] ========== 开始API调用 ==========")

    # 1. Base64编码
    encode_start = time.time()
    print(f"[{encode_start:.3f}] 1. Base64编码开始...")
    audio_b64 = ubinascii.b2a_base64(wav_data)[:-1].decode('utf-8')
    encode_end = time.time()
    encode_time = encode_end - encode_start
    print(f"[{encode_end:.3f}]   ✅ Base64编码完成，数据长度: {len(audio_b64)} 字符")
    print(f"[{encode_end:.3f}]   编码耗时: {encode_time:.3f}秒")

    # 2. 构建请求数据
    build_start = time.time()
    print(f"[{build_start:.3f}] 2. 构建请求数据...")

    payload = {
        "model": MODEL_NAME,
        "input": {
            "messages": [
                {"role": "user", "content": [{"audio": f"data:audio/wav;base64,{audio_b64}"}]}
            ]
        },
        "parameters": {"result_format": "message", "language": "zh-CN"}
    }

    headers = {
        'Authorization': f'Bearer {API_KEY}',
        'Content-Type': 'application/json'
    }

    # 序列化JSON
    json_start = time.time()
    json_data = json.dumps(payload)
    json_end = time.time()

    build_end = time.time()
    build_time = build_end - build_start
    json_time = json_end - json_start

    print(f"[{build_end:.3f}]   ✅ 请求数据构建完成")
    print(f"[{build_end:.3f}]   JSON大小: {len(json_data)} 字节")
    print(f"[{build_end:.3f}]   JSON序列化耗时: {json_time:.3f}秒")
    print(f"[{build_end:.3f}]   总构建耗时: {build_time:.3f}秒")

    # 3. DNS解析
    dns_start = time.time()
    print(f"[{dns_start:.3f}] 3. DNS解析开始...")
    try:
        # 解析域名
        domain = "dashscope.aliyuncs.com"
        dns_resolve_start = time.time()
        addr_info = socket.getaddrinfo(domain, 443)
        dns_resolve_end = time.time()
        ip_address = addr_info[0][4][0]
        dns_time = dns_resolve_end - dns_resolve_start
        print(f"[{time.time():.3f}]   ✅ DNS解析成功")
        print(f"[{time.time():.3f}]   域名: {domain} -> IP: {ip_address}")
        print(f"[{time.time():.3f}]   DNS解析耗时: {dns_time:.3f}秒")
    except Exception as e:
        print(f"[{time.time():.3f}]   ❌ DNS解析失败: {e}")
        return None

    # 4. HTTP请求
    request_start = time.time()
    print(f"[{request_start:.3f}] 4. 发送HTTP请求...")

    try:
        # 发送请求
        send_start = time.time()
        response = requests.post(API_URL, headers=headers, data=json_data, timeout=30)
        send_end = time.time()

        request_time = send_end - send_start
        print(f"[{send_end:.3f}]   ✅ HTTP响应接收完成")
        print(f"[{send_end:.3f}]   状态码: {response.status_code}")
        print(f"[{send_end:.3f}]   HTTP请求耗时: {request_time:.3f}秒")

        # 检查响应大小
        if hasattr(response, 'text'):
            response_size = len(response.text)
            print(f"[{time.time():.3f}]   响应大小: {response_size} 字节")

        # 5. 解析响应
        parse_start = time.time()
        print(f"[{parse_start:.3f}] 5. 解析响应数据...")

        if response.status_code == 200:
            result = response.json()
            text = result['output']['choices'][0]['message']['content'][0]['text']
            parse_end = time.time()
            parse_time = parse_end - parse_start

            print(f"[{parse_end:.3f}]   ✅ 响应解析成功")
            print(f"[{parse_end:.3f}]   解析耗时: {parse_time:.3f}秒")

            # 总耗时统计
            total_end = time.time()
            total_time = total_end - total_start

            print(f"\n[{total_end:.3f}] ========== API调用完成 ==========")
            print(f"[{total_end:.3f}] 识别结果: {text}")
            print(f"[{total_end:.3f}] 各阶段耗时统计:")
            print(f"[{total_end:.3f}]   Base64编码: {encode_time:.3f}秒 ({encode_time / total_time * 100:.1f}%)")
            print(f"[{total_end:.3f}]   请求构建: {build_time:.3f}秒 ({build_time / total_time * 100:.1f}%)")
            print(f"[{total_end:.3f}]   DNS解析: {dns_time:.3f}秒 ({dns_time / total_time * 100:.1f}%)")
            print(f"[{total_end:.3f}]   HTTP请求: {request_time:.3f}秒 ({request_time / total_time * 100:.1f}%)")
            print(f"[{total_end:.3f}]   响应解析: {parse_time:.3f}秒 ({parse_time / total_time * 100:.1f}%)")
            print(f"[{total_end:.3f}]   总耗时: {total_time:.3f}秒")
            print(f"[{total_end:.3f}] ================================\n")

            return text
        else:
            print(f"[{time.time():.3f}]   ❌ API返回错误: {response.status_code}")
            if hasattr(response, 'text'):
                print(f"[{time.time():.3f}]   错误信息: {response.text[:200]}...")
            return None

    except Exception as e:
        error_time = time.time()
        print(f"[{error_time:.3f}]   ❌ HTTP请求失败: {e}")
        print(f"[{error_time:.3f}]   请求总耗时: {error_time - request_start:.3f}秒")
        return None


# --- 主循环 ---
def main():
    total_start_time = time.time()
    print(f"[{total_start_time:.3f}] ====== 语音识别程序启动 ======")

    # 连接Wi-Fi
    if not connect_wifi():
        print(f"[{time.time():.3f}] ❌ Wi-Fi连接失败，程序退出")
        return

    # 检查网络状态
    check_network_status()

    # 测量网络延迟
    measure_network_latency()

    # 内存状态
    gc.collect()
    free_mem = gc.mem_free()
    total_mem = gc.mem_alloc() + free_mem
    print(f"\n[{time.time():.3f}] 内存状态:")
    print(f"[{time.time():.3f}]   总内存: {total_mem} 字节")
    print(f"[{time.time():.3f}]   已用内存: {gc.mem_alloc()} 字节")
    print(f"[{time.time():.3f}]   空闲内存: {free_mem} 字节")
    print(f"[{time.time():.3f}]   使用率: {gc.mem_alloc() / total_mem * 100:.1f}%")

    print(f"\n[{time.time():.3f}] 开始定时采集，每{COLLECT_SECONDS}秒一次\n")

    cycle_count = 0

    while True:
        cycle_count += 1
        cycle_start_time = time.time()
        print(f"\n[{cycle_start_time:.3f}] ====== 第{cycle_count}轮循环开始 ======")

        try:
            # 1. 采集5秒音频
            audio_start = time.time()
            raw_audio = collect_5s_audio()
            audio_end = time.time()
            audio_time = audio_end - audio_start

            # 2. 创建WAV
            wav_start = time.time()
            wav_data = create_wav_441(raw_audio)
            wav_end = time.time()
            wav_time = wav_end - wav_start

            # 3. 调用API（使用详细版本）
            api_start = time.time()
            result = call_api_with_detailed_timing(wav_data)
            api_end = time.time()
            api_time = api_end - api_start

            # 4. 显示本轮统计
            cycle_end_time = time.time()
            cycle_total_time = cycle_end_time - cycle_start_time

            print(f"\n[{cycle_end_time:.3f}] ====== 第{cycle_count}轮循环统计 ======")
            print(f"[{cycle_end_time:.3f}]   音频采集: {audio_time:.2f}秒")
            print(f"[{cycle_end_time:.3f}]   WAV创建: {wav_time:.2f}秒")
            print(f"[{cycle_end_time:.3f}]   API调用: {api_time:.2f}秒")
            print(f"[{cycle_end_time:.3f}]   循环总耗时: {cycle_total_time:.2f}秒")

            # 计算各阶段占比
            print(f"[{cycle_end_time:.3f}]   各阶段占比:")
            print(f"[{cycle_end_time:.3f}]     音频采集: {audio_time / cycle_total_time * 100:.1f}%")
            print(f"[{cycle_end_time:.3f}]     WAV创建: {wav_time / cycle_total_time * 100:.1f}%")
            print(f"[{cycle_end_time:.3f}]     API调用: {api_time / cycle_total_time * 100:.1f}%")
            print(f"[{cycle_end_time:.3f}] ===============================\n")

            # 5. 定期检查和内存清理
            if cycle_count % 3 == 0:  # 每3轮检查一次网络
                gc.collect()
                check_network_status()

            print(f"[{time.time():.3f}] 等待下一轮...\n")

        except KeyboardInterrupt:
            total_end_time = time.time()
            print(f"\n[{total_end_time:.3f}] ====== 程序结束 ======")
            print(f"[{total_end_time:.3f}] 运行总时长: {total_end_time - total_start_time:.2f}秒")
            print(f"[{total_end_time:.3f}] 完成循环数: {cycle_count}")
            break
        except Exception as e:
            error_time = time.time()
            print(f"[{error_time:.3f}] 错误: {e}")
            time.sleep(1)


if __name__ == "__main__":
    main()
