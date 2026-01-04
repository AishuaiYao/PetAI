import pyaudio
import requests
import json
import base64
import time
import numpy as np

# --- 配置 ---
API_KEY = 'sk-943f95da67d04893b70c02be400e2935'
MODEL_NAME = "qwen3-asr-flash"
RESULT_FORMAT = "message"
API_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"

# 音频参数
CHUNK_SIZE = 3200
SAMPLE_RATE = 16000
CHANNELS = 1
AUDIO_FORMAT = pyaudio.paInt16
BYTES_PER_SAMPLE = 2

# VAD参数
SILENCE_THRESHOLD = 0.5
MIN_SPEECH_DURATION = 0.3
ENERGY_THRESHOLD_HIGH = 100000
ENERGY_THRESHOLD_LOW = 1000

# 请求头
HEADERS = {
    'Authorization': f'Bearer {API_KEY}',
    'Content-Type': 'application/json'
}


def calculate_energy(audio_data):
    """计算音频能量"""
    samples = np.frombuffer(audio_data, dtype=np.int16)
    energy = np.sum(samples.astype(np.float32) ** 2) / len(samples)
    return energy


def print_energy_bar(energy, max_energy=5000, width=50):
    """打印能量条"""
    level = min(int((energy / max_energy) * width), width)
    bar = '█' * level + '░' * (width - level)
    status = "🔊 SPEAKING" if energy > ENERGY_THRESHOLD_HIGH else "🔈 LISTENING"
    print(f"\r[{bar}] {energy:6.0f} {status}", end='', flush=True)


def call_asr_api(audio_url):
    """使用requests调用ASR API - 第二种格式"""
    payload = {
        "model": MODEL_NAME,
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "audio": audio_url
                        }
                    ]
                }
            ]
        },
        "parameters": {
            "result_format": RESULT_FORMAT
        }
    }


    response = requests.post(
        API_URL,
        headers=HEADERS,
        data=json.dumps(payload),
        timeout=30
    )

    if response.status_code == 200:
        result = response.json()
        # 解析响应
        try:
            # 尝试标准结构
            text = result['output']['choices'][0]['message']['content'][0]['text']
            return text, True
        except Exception as ex:
            print("error")
            return ex, False
    else:
        print(f"API错误: {response.status_code}")
        print(f"错误信息: {response.text}")
        return None, False



def real_time_asr():
    """核心流式识别逻辑"""
    p = pyaudio.PyAudio()

    stream = p.open(
        format=AUDIO_FORMAT,
        channels=CHANNELS,
        rate=SAMPLE_RATE,
        input=True,
        frames_per_buffer=CHUNK_SIZE
    )

    print("🎤 开始录音，VAD模式... (Ctrl+C停止)")
    print("=" * 50)
    print("能量显示（实时更新）:")

    vad_state = "SILENT"
    speech_buffer = bytearray()
    silence_frames = 0
    speech_frames = 0
    call_count = 0
    last_text = ""

    frame_duration = CHUNK_SIZE / (SAMPLE_RATE * BYTES_PER_SAMPLE)

    try:
        while True:
            audio_data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
            energy = calculate_energy(audio_data)

            # 打印能量条
            print_energy_bar(energy)

            if vad_state == "SILENT":
                if energy > ENERGY_THRESHOLD_HIGH:
                    speech_frames += 1
                    if speech_frames * frame_duration >= MIN_SPEECH_DURATION:
                        vad_state = "SPEAKING"
                        print(f"\n\n🔊 检测到语音开始 (能量: {energy:.0f})")
                        speech_buffer.extend(audio_data)
                else:
                    speech_frames = 0

            elif vad_state == "SPEAKING":
                speech_buffer.extend(audio_data)

                if energy < ENERGY_THRESHOLD_LOW:
                    silence_frames += 1
                    if silence_frames * frame_duration >= SILENCE_THRESHOLD:
                        vad_state = "SILENT"
                        silence_frames = 0
                        speech_frames = 0

                        if len(speech_buffer) > 0:
                            call_count += 1
                            audio_duration = len(speech_buffer) / (SAMPLE_RATE * BYTES_PER_SAMPLE)

                            print(f"\n\n📊 第{call_count}次调用")
                            print(f"语音段: {audio_duration:.2f}秒 ({len(speech_buffer)}字节)")

                            # 转换为WAV格式
                            wav_data = speech_buffer
                            audio_b64 = base64.b64encode(wav_data).decode('utf-8')
                            audio_url = f"data:audio/wav;base64,{audio_b64}"

                            # 调用API
                            start_time = time.time()
                            text, success = call_asr_api(audio_url)
                            api_duration = time.time() - start_time

                            print(f"API耗时: {api_duration:.2f}秒")

                            if success and text:
                                print(f"✅ 识别结果: {text}")
                                last_text = text
                            else:
                                print(f"❌ 识别失败: {text}")

                            print("-" * 50)
                            speech_buffer = bytearray()
                            print("\n继续监听...")
                else:
                    silence_frames = 0

    except KeyboardInterrupt:
        print("\n\n" + "=" * 50)
        print("🎯 识别结束")
        print(f"总调用次数: {call_count}")
        if last_text:
            print(f"最后识别结果: {last_text}")
    except Exception as e:
        print(f"\n程序异常: {e}")
        import traceback
        traceback.print_exc()
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()


if __name__ == "__main__":
    real_time_asr()