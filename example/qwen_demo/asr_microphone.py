import os
import dashscope
import pyaudio
import numpy as np
import threading
import queue
import time
import base64

# --- 配置 ---
API_KEY = 'sk-943f95da67d04893b70c02be400e2935'
dashscope.api_key = API_KEY

# 音频参数
CHUNK = 3200  # 音频块大小
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000  # ASR通常用16kHz


class RealTimeStreamingASR:
    def __init__(self):
        self.audio_queue = queue.Queue()
        self.is_recording = True
        self.last_text = ""

        # 初始化音频
        self.p = pyaudio.PyAudio()

    def audio_capture(self):
        """实时捕获麦克风音频"""
        stream = self.p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            frames_per_buffer=CHUNK,
            stream_callback=self.audio_callback
        )

        print("🎤 开始录音... (按Ctrl+C停止)")
        stream.start_stream()

        try:
            while self.is_recording and stream.is_active():
                time.sleep(0.1)
        finally:
            stream.stop_stream()
            stream.close()

    def audio_callback(self, in_data, frame_count, time_info, status):
        """PyAudio回调函数"""
        if status:
            print(f"音频状态: {status}")
        self.audio_queue.put(in_data)
        return (None, pyaudio.paContinue)

    def send_audio_stream(self):
        """尝试使用流式API发送音频"""
        print("正在连接到ASR流式API...")

        # 尝试直接调用，看看ASR是否支持stream=True
        try:
            # 先测试一下API
            test_response = dashscope.MultiModalConversation.call(
                model="qwen3-asr-flash",
                messages=[{"role": "user", "content": [{"audio": "data:audio/wav;base64,//tQ"}]}],
                result_format="message"
            )
            print(f"API测试响应: {test_response.status_code}")

        except Exception as e:
            print(f"API测试失败: {e}")
            return

        # 尝试流式处理
        buffer = bytearray()
        while self.is_recording or not self.audio_queue.empty():
            try:
                # 收集音频数据
                start_time = time.time()
                while len(buffer) < RATE * 2 * 2 and time.time() - start_time < 1.0:
                    try:
                        audio_data = self.audio_queue.get(timeout=0.1)
                        buffer.extend(audio_data)
                    except queue.Empty:
                        if not self.is_recording:
                            break
                        continue

                if len(buffer) > RATE * 1:  # 至少有1秒音频
                    # 转换为base64
                    audio_b64 = base64.b64encode(buffer).decode('utf-8')
                    audio_url = f"data:audio/wav;base64,{audio_b64}"

                    print(f"发送 {len(buffer) / RATE / 2:.1f} 秒音频...")

                    # 尝试流式调用 - 关键在这里！
                    try:
                        response = dashscope.MultiModalConversation.call(
                            model="qwen3-asr-flash",
                            messages=[{"role": "user", "content": [{"audio": audio_url}]}],
                            result_format="message",
                            stream=True  # 尝试启用流式
                        )

                        # 如果是流式响应，应该可以迭代
                        if hasattr(response, '__iter__'):
                            print("✅ 检测到流式响应!")
                            for chunk in response:
                                if chunk.status_code == 200 and chunk.output:
                                    try:
                                        text = chunk.output.choices[0].message.content[0]['text']
                                        if text != self.last_text:
                                            print(f"📝 {text}")
                                            self.last_text = text
                                    except:
                                        pass
                        else:
                            # 非流式响应
                            if response.status_code == 200:
                                text = response.output.choices[0].message.content[0]['text']
                                if text != self.last_text:
                                    print(f"📝 {text}")
                                    self.last_text = text

                    except Exception as e:
                        print(f"API调用错误: {e}")
                        # 如果流式失败，回退到非流式
                        try:
                            response = dashscope.MultiModalConversation.call(
                                model="qwen3-asr-flash",
                                messages=[{"role": "user", "content": [{"audio": audio_url}]}],
                                result_format="message"
                            )
                            if response.status_code == 200:
                                text = response.output.choices[0].message.content[0]['text']
                                if text != self.last_text:
                                    print(f"📝 {text}")
                                    self.last_text = text
                        except:
                            pass

                    # 保留最后0.5秒作为上下文
                    buffer = buffer[-int(RATE * 0.5 * 2):]

            except Exception as e:
                print(f"处理错误: {e}")
                time.sleep(0.5)

    def run(self):
        # 启动录音线程
        record_thread = threading.Thread(target=self.audio_capture, daemon=True)
        record_thread.start()

        time.sleep(1)  # 等待录音开始

        # 启动处理线程
        process_thread = threading.Thread(target=self.send_audio_stream, daemon=True)
        process_thread.start()

        try:
            while True:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\n正在停止...")
        finally:
            self.is_recording = False
            self.p.terminate()
            print("👋 程序结束")


# --- 简化版本：模仿TTS的流式风格 ---

def try_real_streaming():
    """尝试真正的流式ASR"""
    print("=== 尝试流式ASR ===")

    # 检查ASR是否支持stream参数
    dashscope.api_key = API_KEY

    # 先录制一小段音频测试
    import sounddevice as sd

    print("录制5秒测试音频...")
    test_audio = sd.rec(int(5 * 16000), samplerate=16000, channels=1, dtype='int16')
    sd.wait()

    # 转换为base64
    audio_bytes = test_audio.tobytes()
    audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')
    audio_url = f"data:audio/wav;base64,{audio_b64}"

    print("测试流式API...")

    try:
        # 关键：尝试 stream=True
        response = dashscope.MultiModalConversation.call(
            model="qwen3-asr-flash",
            messages=[{"role": "user", "content": [{"audio": audio_url}]}],
            result_format="message",
            stream=True  # 这个参数可能被ASR忽略
        )

        # 检查响应类型
        print(f"响应类型: {type(response)}")

        if hasattr(response, '__iter__'):
            print("✅ ASR支持流式响应!")
            for chunk in response:
                print(f"收到chunk: {chunk.status_code}")
                if chunk.status_code == 200:
                    try:
                        text = chunk.output.choices[0].message.content[0]['text']
                        print(f"识别: {text}")
                    except:
                        pass
        else:
            print("❌ ASR可能不支持stream=True")
            print(f"识别结果: {response.output.choices[0].message.content[0]['text']}")

    except Exception as e:
        print(f"错误: {e}")
        print("ASR不支持真正的流式，使用准实时模式")


# --- 主程序 ---
if __name__ == "__main__":
    print("检查ASR流式支持...")

    # 方法1：测试流式支持
    # try_real_streaming()

    # 方法2：运行流式ASR
    asr = RealTimeStreamingASR()
    asr.run()