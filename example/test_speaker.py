from machine import I2S, Pin

# 启用功放：GPIO21置高（MAX98375必需）
Pin(21, Pin.OUT).value(1)

# 初始化I2S（保留必填参数，简化配置）
i2s = I2S(
    0,
    sck=Pin(9),
    ws=Pin(10),
    sd=Pin(8),
    mode=I2S.TX,
    bits=16,
    format=I2S.STEREO,
    rate=44100,
    ibuf=10000
)

# 核心改动：不用正弦波，直接生成固定值的音频缓冲区
# 16位音频的固定值（范围-32768~32767，选2000是适中音量，不爆音）
FIXED_VALUE = 2000
# 生成缓冲区（128个立体声采样，每个4字节）
buf = bytearray(128 * 4)
for i in range(0, len(buf), 4):
    # 按16位小端序填充固定值（左右声道都用同一个固定值）
    # 低字节：FIXED_VALUE & 0xFF，高字节：(FIXED_VALUE >> 8) & 0xFF
    buf[i] = FIXED_VALUE & 0xFF
    buf[i+1] = (FIXED_VALUE >> 8) & 0xFF
    buf[i+2] = FIXED_VALUE & 0xFF
    buf[i+3] = (FIXED_VALUE >> 8) & 0xFF

# 持续播放固定值音频
try:
    while 1:
        i2s.write(buf)
except:
    # 异常时清理资源
    Pin(21, Pin.OUT).value(0)
    i2s.deinit()
