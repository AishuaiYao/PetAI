# 导入 MicroPython 硬件控制和延时模块
from machine import Pin
import time
from neopixel import NeoPixel

# 配置 RGB 灯：引脚 48（手册指定），1 个灯珠（板载 WS2818）
rgb_pin = Pin(48, Pin.OUT)
np = NeoPixel(rgb_pin, 1)

# 定义颜色（RGB 格式，数值 0-255 调节亮度）
RED = (255, 0, 0)  # 红色
GREEN = (0, 255, 0)  # 绿色
BLUE = (0, 0, 255)  # 蓝色
WHITE = (255, 255, 255)  # 白色
OFF = (0, 0, 0)  # 熄灭

# 循环切换颜色，点亮 RGB 灯
while True:
    np[0] = RED  # 设置第 1 个灯珠为红色
    np.write()  # 发送颜色数据到 RGB 灯
    time.sleep(1)  # 保持 1 秒

    np[0] = GREEN  # 切换为绿色
    np.write()
    time.sleep(1)

    np[0] = BLUE  # 切换为蓝色
    np.write()
    time.sleep(1)

    np[0] = WHITE  # 切换为白色
    np.write()
    time.sleep(1)

    np[0] = OFF  # 熄灭
    np.write()
    time.sleep(1)
