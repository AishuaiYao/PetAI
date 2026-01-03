import os
import base64
import dashscope
import sounddevice as sd
import numpy as np

# --- 1. 配置 ---

# 请直接在这里填入你的Dashscope API Key
# 获取地址：https://dashscope.console.aliyun.com/api-key
API_KEY = 'sk-943f95da67d04893b70c02be400e2935'  # <--- 在这里替换成你自己的API Key

# 音频参数
SAMPLE_RATE = 16000  # 采样率
RECORD_SECONDS = 5   # 录制时长（秒）

# --- 2. 录制音频并转换为Base64 Data URL ---

print(f"准备录制 {RECORD_SECONDS} 秒音频，请开始说话...")

# 录制音频
audio_data = sd.rec(int(SAMPLE_RATE * RECORD_SECONDS), samplerate=SAMPLE_RATE, channels=1, dtype='int16')
sd.wait()  # 等待录制完成
print("录制完成！")

# 将NumPy数组格式的音频数据转换为原始的字节流（bytes）
audio_bytes = audio_data.tobytes()

# 将字节流编码为Base64字符串
base64_audio = base64.b64encode(audio_bytes).decode('utf-8')

# 构建Data URL
audio_data_url = f"data:audio/wav;base64,{base64_audio}"

# --- 3. 调用千问ASR API ---

# 配置Dashscope
dashscope.api_key = API_KEY

print("正在将音频发送到千问API进行识别...")

try:
    messages = [
        {"role": "user", "content": [{"audio": audio_data_url}]}
    ]

    response = dashscope.MultiModalConversation.call(
        model="qwen3-asr-flash",
        messages=messages,
        result_format="message",
        asr_options={
            "enable_itn": False
        }
    )

    # --- 4. 处理并打印结果 (增加了健壮性检查) ---

    # 首先，检查最外层的状态码
    if response.status_code == 200:
        # 然后，检查 choices 列表是否存在且不为空
        if response.output and response.output.choices and len(response.output.choices) > 0:
            choice = response.output.choices[0]
            # 接着，检查 content 列表是否存在且不为空
            if choice.message and choice.message.content and len(choice.message.content) > 0:
                content_part = choice.message.content[0]
                # 最后，检查是否包含 'text' 字段
                if 'text' in content_part:
                    recognized_text = content_part['text']
                    print("\n--- 识别结果 ---")
                    print(recognized_text)
                    print("------------------")
                else:
                    print("解析失败：返回的内容中不包含 'text' 字段。")
                    print("完整的返回内容:", response.output.choices[0].message.content)
            else:
                print("解析失败：'message.content' 列表为空或不存在。")
        else:
            print("解析失败：'output.choices' 列表为空或不存在。这可能意味着音频未能被识别。")
            # 打印完整的response对象，方便调试
            print("完整的API响应:", response)
    else:
        # 如果HTTP状态码不是200，直接打印API的错误信息
        print(f"API调用失败: Status Code: {response.status_code}, Code: {response.code}, Message: {response.message}")

except Exception as e:
    # 捕获其他所有可能的异常
    print(f"发生未知错误: {e}")