# 导入math模块（用于生成正弦波）和machine模块中的I2S、Pin类（硬件控制）
import math
from machine import I2S, Pin

# 引脚+功放启用：配置GPIO21为输出模式，并置高电平（MAX98375的SD引脚，置高启用功放）
Pin(21, Pin.OUT).value(1)

# I2S初始化（添加必填的ibuf参数）
# 0：I2S通道号；sck=Pin(9)：串行时钟引脚；ws=Pin(10)：左右声道时钟引脚
# sd=Pin(8)：数据输出引脚；mode=I2S.TX：发送模式（输出音频）
# bits=16：音频采样位数16位；format=I2S.STEREO：立体声模式
# rate=44100：采样率44100Hz；ibuf=10000：内部缓冲区大小（必填参数）
i2s = I2S(0, sck=Pin(9), ws=Pin(10), sd=Pin(8), mode=I2S.TX, bits=16, format=I2S.STEREO, rate=44100, ibuf=10000)

# 生成音频缓冲区：创建128*4字节的字节数组（128个立体声采样，每个采样4字节：左2字节+右2字节）
buf = bytearray(128*4)
# 初始化相位p=0.0，相位增量pi=2π*音频频率/采样率（440Hz是A调基准音）
p, pi = 0.0, 2*math.pi*440/44100
# 循环填充缓冲区：步长4（对应每个立体声采样的4字节）
for i in range(0, len(buf), 4):
    # 计算正弦波采样值：振幅3000（控制音量）*正弦相位值，转为整数
    s = int(3000*math.sin(p))
    # 按16位立体声小端序填充缓冲区：左声道低字节→左声道高字节→右声道低字节→右声道高字节
    buf[i:i+4] = bytes([s&0xff, (s>>8)&0xff, s&0xff, (s>>8)&0xff])
    # 更新相位：相位累加增量，超过2π（360度）则重置为0，避免数值溢出
    p = p+pi if p<2*math.pi else 0

# 持续发声（异常捕获，防止程序崩溃）
try:
    # 无限循环：持续向I2S总线写入音频缓冲区，喇叭持续出声
    while 1:
        i2s.write(buf)
# 捕获所有异常（如按Ctrl+C中断、硬件错误等）
except:
    # 异常触发时：关闭功放（GPIO21置低），保护硬件
    Pin(21, Pin.OUT).value(0)
    # 释放I2S资源，关闭I2S总线
    i2s.deinit()