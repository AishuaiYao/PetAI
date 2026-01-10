import os
import dashscope
import pyaudio
import time
import base64
import numpy as np

# 配置DashScope
dashscope.base_http_api_url = 'https://dashscope.aliyuncs.com/api/v1'

# 初始化音频播放
p = pyaudio.PyAudio()
stream = p.open(format=pyaudio.paInt16,
                channels=1,
                rate=24000,
                output=True)

text = "你好作者你好啊，现在是tts测试"
response = dashscope.MultiModalConversation.call(
    api_key='sk-943f95da67d04893b70c02be400e2935',
    model="qwen3-tts-flash",
    text=text,
    voice="Cherry",
    language_type="Chinese",
    stream=True
)

all_audio_pcm = b''  # 收集纯裸PCM数据（无任何头）
first_chunk_analyzed = False  # 标记是否已分析第一个音频块

for chunk in response:
    if chunk.output is not None:
        audio = chunk.output.audio
        if audio.data is not None:
            wav_bytes = base64.b64decode(audio.data)
            all_audio_pcm += wav_bytes  # 直接收集原始PCM

            # 只分析第一个音频块的属性（所有块格式一致）
            if not first_chunk_analyzed:
                print("=" * 50)
                print("音频数据属性分析结果：")
                print("=" * 50)

                # 1. 基础字节信息
                print(f"当前音频块字节长度: {len(wav_bytes)} bytes")
                print(f"每个采样点的字节数: {np.dtype(np.int16).itemsize} bytes")

                # 2. 采样位数判断
                sample_bits = np.dtype(np.int16).itemsize * 8
                print(f"采样位数: {sample_bits} bit")

                # 3. 数据类型判断
                print(f"数据类型: {np.int16} (16位有符号整数)")
                print(f"是否浮点数: {np.issubdtype(np.int16, np.floating)}")

                # 4. 计算该帧的采样点数和时长
                sample_count = len(wav_bytes) // np.dtype(np.int16).itemsize
                frame_duration = sample_count / 24000  # 采样率24000Hz
                print(f"当前帧采样点数: {sample_count} 个")
                print(f"当前帧时长: {frame_duration:.4f} 秒")

                # 5. 数据范围检查
                audio_np = np.frombuffer(wav_bytes, dtype=np.int16)
                print(f"数据值范围: [{np.min(audio_np)}, {np.max(audio_np)}]")
                print(f"数据平均值: {np.mean(audio_np):.2f}")

                first_chunk_analyzed = True
                print("=" * 50)

            # 播放音频
            audio_np = np.frombuffer(wav_bytes, dtype=np.int16)
            stream.write(audio_np.tobytes())

        if chunk.output.finish_reason == "stop":
            print("\nTTS音频收集完成")

# 分析整体音频数据
print("\n" + "=" * 50)
print("整体音频数据统计：")
print("=" * 50)
total_samples = len(all_audio_pcm) // np.dtype(np.int16).itemsize
total_duration = total_samples / 24000
print(f"总字节数: {len(all_audio_pcm)} bytes")
print(f"总采样点数: {total_samples} 个")
print(f"总时长: {total_duration:.2f} 秒")

# 保存纯裸PCM文件（无WAV头，后缀名.pcm）
with open("tts_raw.pcm", "wb") as f:  # 修正文件名后缀
    f.write(all_audio_pcm)
print(f"\n纯裸PCM文件已生成：tts_raw.pcm（{sample_bits}位单声道24000Hz）")

# 清理资源
time.sleep(0.8)
stream.stop_stream()
stream.close()
p.terminate()