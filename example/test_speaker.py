from machine import I2S, Pin

# 1. 启用功放（MAX98375的SD引脚，GPIO21置高）
Pin(21, Pin.OUT).value(1)

# 2. 初始化I2S（核心改：format=I2S.MONO 单声道）
i2s = I2S(
    0,                  # I2S通道号
    sck=Pin(9),         # 串行时钟引脚
    ws=Pin(10),         # 声道时钟引脚（单声道仍需，硬件协议要求）
    sd=Pin(8),          # 数据输出引脚
    mode=I2S.TX,        # 发送模式（输出音频）
    bits=16,            # 16位采样（单声道下1帧=2字节）
    format=I2S.MONO,    # 单声道模式（核心修改）
    rate=44100,         # 采样率44100Hz
    ibuf=10000          # 必填缓冲区参数，避免报错
)

# 3. 生成单声道音频缓冲区（1帧=2字节，更省资源）
FIXED_VALUE = 2000  # 固定音频值（音量，1000-5000为宜）
buf = bytearray(128 * 2)  # 128帧 × 2字节/帧 = 256字节缓冲区
for i in range(0, len(buf), 2):  # 步长2，每次处理1帧（单声道）
    # 16位小端序填充固定值：低字节 → 高字节
    buf[i] = FIXED_VALUE & 0xFF        # 低8位
    buf[i+1] = (FIXED_VALUE >> 8) & 0xFF  # 高8位

# 4. 持续播放（异常捕获保护硬件）
try:
    while 1:
        i2s.write(buf)  # 循环发送单声道音频数据
except:
    # 异常时（如Ctrl+C）：关闭功放+释放I2S资源
    Pin(21, Pin.OUT).value(0)
    i2s.deinit()
