import os
import dashscope
import pyaudio
import time
import base64
import numpy as np

dashscope.base_http_api_url = 'https://dashscope.aliyuncs.com/api/v1'

p = pyaudio.PyAudio()
stream = p.open(format=pyaudio.paInt16,
                channels=1,
                rate=24000,
                output=True)

text = "这个错误的意思是"
response = dashscope.MultiModalConversation.call(
    api_key='sk-943f95da67d04893b70c02be400e2935',
    model="qwen3-tts-flash",
    text=text,
    voice="Cherry",
    language_type="Chinese",
    stream=True
)

all_audio_pcm = b''  # 收集纯裸PCM数据（无任何头）
for chunk in response:
    if chunk.output is not None:
        audio = chunk.output.audio
        if audio.data is not None:
            wav_bytes = base64.b64decode(audio.data)
            all_audio_pcm += wav_bytes  # 直接收集原始PCM
            audio_np = np.frombuffer(wav_bytes, dtype=np.int16)
            stream.write(audio_np.tobytes())
        if chunk.output.finish_reason == "stop":
            print("TTS音频收集完成")

# 保存纯裸PCM文件（无WAV头，后缀名.pcm）
with open("tts_raw.pcm", "wb") as f:
    f.write(all_audio_pcm)
print("纯裸PCM文件已生成：tts_raw.pcm（16位单声道24000Hz）")

# 清理资源
time.sleep(0.8)
stream.stop_stream()
stream.close()
p.terminate()