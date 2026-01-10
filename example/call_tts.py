import urequests, json, uasyncio, ubinascii, gc
from machine import I2S, Pin

# 基础配置
WIFI_SSID = "CMCC-huahua"
WIFI_PASSWORD = "*HUAHUAshi1zhimao"
API_KEY = 'sk-943f95da67d04893b70c02be400e2935'
TEXT = "测试一下声音"

# 引脚配置
BCLK_PIN, LRC_PIN, DIN_PIN, SD_PIN, GAIN_PIN = 18, 3, 19, 21, 20


class TTSService:
    def __init__(self, api_key):
        # I2S初始化
        self.audio_out = I2S(1, sck=Pin(BCLK_PIN), ws=Pin(LRC_PIN), sd=Pin(DIN_PIN),
                             mode=I2S.TX, bits=16, format=I2S.MONO, rate=24000, ibuf=8192)
        # MAX98357控制
        self.max_sd = Pin(SD_PIN, Pin.OUT, value=0)
        self.max_gain = Pin(GAIN_PIN, Pin.OUT, value=1)
        self.api_key = api_key
        self.api_url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"

    def test_sound(self):
        # 生成测试音
        samples = bytearray(4800)
        for i in range(2400):
            val = 8000 if (i // 12) % 2 == 0 else -8000
            samples[i * 2], samples[i * 2 + 1] = val & 0xFF, (val >> 8) & 0xFF
        self.audio_out.write(samples)
        return True

    def _parse_sse(self, line):
        if not line or not line.startswith('data:'):
            return None
        json_str = line[5:].strip()
        if json_str == '[DONE]':
            return {"type": "done"}
        try:
            return {"type": "data", "data": json.loads(json_str)}
        except:
            return None

    def _play_audio(self, audio_data):
        # 解码并播放音频块
        wav = ubinascii.a2b_base64(audio_data)
        if len(wav) > 44:
            pcm = wav[44:]
            # 分块写入
            for i in range(0, len(pcm), 1024):
                self.audio_out.write(pcm[i:i + 1024])

    async def synthesize_speech(self, text):
        try:
            # 构建请求
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json",
                       "X-DashScope-SSE": "enable"}
            payload = {"model": "qwen3-tts-flash", "input": {"text": text},
                       "parameters": {"voice": "Cherry", "language_type": "Chinese", "format": "wav",
                                      "sample_rate": 24000}}

            # 发送请求
            resp = urequests.post(self.api_url, headers=headers, data=json.dumps(payload))
            if resp.status_code != 200:
                resp.close()
                return False

            # 解析响应
            content = resp.content.decode('utf-8', 'ignore')
            resp.close()
            lines = content.replace('\r\n', '\n').split('\n')

            count = 0
            for line in lines:
                line = line.strip()
                parsed = self._parse_sse(line)
                if not parsed:
                    continue
                if parsed["type"] == "done":
                    break
                if "output" in parsed["data"] and "audio" in parsed["data"]["output"]:
                    audio = parsed["data"]["output"]["audio"]
                    if "data" in audio and audio["data"]:
                        count += 1
                        self._play_audio(audio["data"])
            return count > 0
        except:
            return False

    def cleanup(self):
        self.audio_out.deinit()
        self.max_sd.value(1)
        gc.collect()


async def main():
    tts = TTSService(API_KEY)
    try:
        tts.test_sound()
        await uasyncio.sleep(0.5)
        await tts.synthesize_speech(TEXT)
    finally:
        tts.cleanup()


def connect_wifi():
    import network, time
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        for _ in range(30):
            if wlan.isconnected():
                break
            time.sleep(0.5)
    return wlan.isconnected()


if __name__ == "__main__":
    if connect_wifi():
        uasyncio.run(main())
