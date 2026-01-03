#  DashScope SDK 版本不低于 1.24.6
# coding=utf-8
#
# Installation instructions for pyaudio:
# APPLE Mac OS X
#   brew install portaudio
#   pip install pyaudio
# Debian/Ubuntu
#   sudo apt-get install python-pyaudio python3-pyaudio
#   or
#   pip install pyaudio
# CentOS
#   sudo yum install -y portaudio portaudio-devel && pip install pyaudio
# Microsoft Windows
#   python -m pip install pyaudio

import os
import dashscope
import pyaudio
import time
import base64
import numpy as np

# 以下为北京地域url，若使用新加坡地域的模型，需将url替换为：https://dashscope-intl.aliyuncs.com/api/v1
dashscope.base_http_api_url = 'https://dashscope.aliyuncs.com/api/v1'

p = pyaudio.PyAudio()
# 创建音频流
stream = p.open(format=pyaudio.paInt16,
                channels=1,
                rate=24000,
                output=True)


text = "这个错误的意思是，你的程序在尝试调用阿里云通义千问（DashScope）的 API 时，没有提供有效的 API 密钥（API Key）。"
response = dashscope.MultiModalConversation.call(
    # 新加坡和北京地域的API Key不同。获取API Key：https://help.aliyun.com/zh/model-studio/get-api-key
    # 若没有配置环境变量，请用百炼API Key将下行替换为：api_key = "sk-xxx"
    api_key='sk-943f95da67d04893b70c02be400e2935',
    model="qwen3-tts-flash",
    text=text,
    voice="Cherry",
    language_type="Chinese",  # 建议与文本语种一致，以获得正确的发音和自然的语调。
    stream=True
)

for chunk in response:
    if chunk.output is not None:
      audio = chunk.output.audio
      if audio.data is not None:
          wav_bytes = base64.b64decode(audio.data)
          audio_np = np.frombuffer(wav_bytes, dtype=np.int16)
          # 直接播放音频数据
          stream.write(audio_np.tobytes())
      if chunk.output.finish_reason == "stop":
          print("finish at: {} ", chunk.output.audio.expires_at)
time.sleep(0.8)
# 清理资源
stream.stop_stream()
stream.close()
p.terminate()