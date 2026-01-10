import machine
import math
from machine import I2S, Pin

# 核心引脚定义（仅保留必须的）
lrc_pin = Pin(10)
sck_pin = Pin(9)
dout_pin = Pin(8)
sd_pin = Pin(21, Pin.OUT)

# 启用功放（直接设置电平，去掉函数封装）
sd_pin.value(1)  # MAX98375 SD引脚置高，启用功放

# 初始化I2S（最简配置）
i2s = I2S(
    0,
    sck=sck_pin,
    ws=lrc_pin,
    sd=dout_pin,
    mode=I2S.TX,
    bits=16,
    format=I2S.STEREO,
    rate=44100,
    ibuf=10000  # 减小缓冲区，简化配置
)

# 音频核心参数（仅保留必要的）
SAMPLE_RATE = 44100
TONE_FREQ = 440  # 440Hz（A调），更柔和易听
AMPLITUDE = 3000
BUFFER_SIZE = 128  # 减小缓冲区，简化

# 生成基础正弦波缓冲区（提前生成一次，循环使用）
buffer = bytearray(BUFFER_SIZE * 4)
phase = 0.0
phase_inc = 2 * math.pi * TONE_FREQ / SAMPLE_RATE
for i in range(0, len(buffer), 4):
    sample = int(AMPLITUDE * math.sin(phase))
    # 16位立体声小端序填充
    buffer[i] = sample & 0xFF
    buffer[i + 1] = (sample >> 8) & 0xFF
    buffer[i + 2] = sample & 0xFF
    buffer[i + 3] = (sample >> 8) & 0xFF
    phase += phase_inc
    if phase > 2 * math.pi:
        phase -= 2 * math.pi

# 无限循环输出音频（核心功能）
try:
    while True:
        i2s.write(buffer)  # 持续发送音频缓冲区
except KeyboardInterrupt:
    # 仅保留必要的清理
    sd_pin.value(0)  # 关闭功放
    i2s.deinit()