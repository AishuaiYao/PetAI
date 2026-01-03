import pyaudio
import dashscope
import base64
import time

# --- 配置 ---
API_KEY = 'sk-943f95da67d04893b70c02be400e2935'
dashscope.api_key = API_KEY

# 音频参数
CHUNK = 3200  # 0.2秒音频 (16000Hz * 0.2s * 2字节 = 3200)
RATE = 16000


def real_time_asr():
    """核心流式识别逻辑"""
    p = pyaudio.PyAudio()

    # 打开音频流
    stream = p.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=RATE,
        input=True,
        frames_per_buffer=CHUNK
    )

    print("🎤 开始录音，正在实时识别... (Ctrl+C停止)")
    print("=" * 50)

    buffer = bytearray()  # 音频缓冲区
    last_text = ""  # 上一次识别结果
    call_count = 0  # 调用次数统计

    try:
        while True:
            # 1. 读取音频数据
            audio_data = stream.read(CHUNK, exception_on_overflow=False)
            buffer.extend(audio_data)

            # 2. 当有2秒音频时进行识别
            if len(buffer) >= RATE * 2 * 2:  # 2秒 = RATE * 秒数 * 2字节
                call_count += 1

                # 计算音频时长
                audio_duration = len(buffer) / (RATE * 2)  # 字节数 / (采样率 * 2字节)

                # 转换为base64
                audio_b64 = base64.b64encode(buffer).decode('utf-8')
                audio_url = f"data:audio/wav;base64,{audio_b64}"

                print(f"\n📊 第{call_count}次调用")
                print(f"输入音频: {audio_duration:.2f}秒 ({len(buffer)}字节)")

                # 3. 调用API（尝试流式）
                start_time = time.time()

                try:
                    response = dashscope.MultiModalConversation.call(
                        model="qwen3-asr-flash",
                        messages=[{"role": "user", "content": [{"audio": audio_url}]}],
                        result_format="message",
                        stream=True  # 尝试流式
                    )

                    api_duration = time.time() - start_time
                    print(f"API耗时: {api_duration:.3f}秒")

                    # 4. 处理响应
                    if hasattr(response, '__iter__'):  # 如果是流式
                        print("🔁 流式响应模式")
                        for chunk in response:
                            if chunk.status_code == 200:
                                text = chunk.output.choices[0].message.content[0]['text']
                                if text != last_text:
                                    print(f"识别结果: {text}")
                                    last_text = text
                    else:  # 如果不是流式
                        print("🔄 普通响应模式")
                        if response.status_code == 200:
                            text = response.output.choices[0].message.content[0]['text']
                            if text != last_text:
                                print(f"识别结果: {text}")
                                last_text = text
                        else:
                            print(f"API错误: {response.code}")

                except Exception as e:
                    api_duration = time.time() - start_time
                    print(f"API耗时: {api_duration:.3f}秒")
                    print(f"API异常: {e}")

                # 5. 计算处理速度（避免除零错误）
                if api_duration > 0:
                    speed_ratio = audio_duration / api_duration
                    print(f"处理速度: {speed_ratio:.1f}倍速")
                else:
                    print("处理速度: 极快 (<0.001秒)")

                print("-" * 40)

                # 6. 保留最后0.5秒作为上下文
                buffer = buffer[-int(RATE * 0.5 * 2):]

            time.sleep(0.05)  # 稍微降低CPU使用

    except KeyboardInterrupt:
        print("\n" + "=" * 50)
        print("🎯 识别结束")
        print(f"总调用次数: {call_count}")
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()


if __name__ == "__main__":
    real_time_asr()