import math
from machine import I2S, Pin

# 引脚+功放启用
Pin(21, Pin.OUT).value(1)

# I2S初始化（添加必填的ibuf参数）
i2s = I2S(0, sck=Pin(9), ws=Pin(10), sd=Pin(8), mode=I2S.TX, bits=16, format=I2S.STEREO, rate=44100, ibuf=10000)

# 生成音频缓冲区
buf = bytearray(128*4)
p, pi = 0.0, 2*math.pi*440/44100
for i in range(0, len(buf), 4):
    s = int(3000*math.sin(p))
    buf[i:i+4] = bytes([s&0xff, (s>>8)&0xff, s&0xff, (s>>8)&0xff])
    p = p+pi if p<2*math.pi else 0

# 持续发声
try:
    while 1:
        i2s.write(buf)
except:
    Pin(21, Pin.OUT).value(0)
    i2s.deinit()
