from machine import I2S, Pin

# 1. 硬件初始化（严格匹配PCM格式：16位单声道24000Hz）
Pin(21, Pin.OUT).value(1)  # 启用功放
i2s = I2S(
    0,
    sck=Pin(9),
    ws=Pin(10),
    sd=Pin(8),
    mode=I2S.TX,
    bits=16,            # 匹配PCM：16位
    format=I2S.MONO,    # 匹配PCM：单声道
    rate=24000,         # 匹配PCM：24000Hz采样率
    ibuf=30000          # 足够大的缓冲区，避免卡顿
)

# 2. 直接播放裸PCM文件（无任何格式解析）
def play_raw_pcm(file_path):
    try:
        print("开始播放裸PCM音频...")
        with open(file_path, "rb") as f:
            buf = bytearray(1024)  # 播放缓冲区
            while True:
                # 读取裸PCM数据
                num_read = f.readinto(buf)
                if num_read == 0:
                    break  # 播放完毕
                # 直接发送到I2S，无需任何处理
                i2s.write(buf[:num_read])
        print("PCM音频播放完成！")
    except Exception as e:
        print(f"播放失败：{e}")
    finally:
        # 无论是否出错，都关闭功放、释放I2S
        Pin(21, Pin.OUT).value(0)
        i2s.deinit()

# 3. 执行播放（需先把tts_raw.pcm上传到开发板根目录）
play_raw_pcm("tts_raw.pcm")
