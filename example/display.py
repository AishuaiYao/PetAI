# 导入必要模块（和你的单屏代码完全一致）
from machine import Pin, SPI, reset as machine_reset
import gc9a01
import time
import gc

# -------------------------- 双屏引脚硬编码（完全避开SPI属性访问） --------------------------
# ========== Display1 配置（和你的单屏代码100%一致） ==========
# 引脚定义
dc1_pin = Pin(41, Pin.OUT)
cs1_pin = Pin(40, Pin.OUT)
reset1_pin = Pin(42, Pin.OUT)
backlight1_pin = Pin(39, Pin.OUT)
# SPI引脚硬编码（直接写死，不访问SPI对象属性）
sck1 = 1
mosi1 = 2

# ========== Display2 配置（全合法GPIO，硬编码） ==========
# （vcc gnd  scl：1 sda：2 res：42 dc：41 cs：40 blk：39）
# display2（vcc gnd  scl：38 sda：37res：36dc：45 cs：48 blk：47）用这个引脚用两个spi驱动双屏
dc2_pin = Pin(45, Pin.OUT)
cs2_pin = Pin(48, Pin.OUT)
reset2_pin = Pin(14, Pin.OUT)
backlight2_pin = Pin(47, Pin.OUT)
# SPI引脚硬编码
sck2 = 38
mosi2 = 13

# -------------------------- 强制初始化所有引脚状态（复用你的单屏逻辑） --------------------------
# Display1 引脚默认状态
cs1_pin.value(1)
dc1_pin.value(0)
reset1_pin.value(1)
backlight1_pin.value(0)

# Display2 引脚默认状态
cs2_pin.value(1)
dc2_pin.value(0)
reset2_pin.value(1)
backlight2_pin.value(0)

# -------------------------- SPI总线配置（硬编码引脚，无属性访问） --------------------------
# Display1：SPI2（和你的单屏代码一致）
spi1 = SPI(
    2,
    baudrate=20000000,
    sck=Pin(sck1, Pin.OUT),  # 直接用硬编码引脚号
    mosi=Pin(mosi1, Pin.OUT),
    miso=None,
    polarity=0,
    phase=0,
    firstbit=SPI.MSB
)

# Display2：SPI1（参数和Display1完全一致）
spi2 = SPI(
    1,
    baudrate=20000000,
    sck=Pin(sck2, Pin.OUT),  # 直接用硬编码引脚号
    mosi=Pin(mosi2, Pin.OUT),
    miso=None,
    polarity=0,
    phase=0,
    firstbit=SPI.MSB
)

# -------------------------- 初始化函数（完全硬编码，无SPI属性访问） --------------------------
def init_display(spi, dc_pin, cs_pin, reset_pin, backlight_pin, sck_pin, mosi_pin):
    """
    初始化屏幕（完全复用你的单屏逻辑，仅传入硬编码引脚号）
    """
    # 复位步骤添加打印
    print("执行硬件复位...")
    reset_pin.value(0)
    time.sleep_ms(100)
    reset_pin.value(1)
    time.sleep_ms(200)
    print("复位完成")
    # 2. 重新初始化SPI（直接用硬编码引脚，不访问SPI对象属性）
    spi.deinit()
    time.sleep_ms(50)
    spi.init(
        baudrate=20000000,
        sck=Pin(sck_pin, Pin.OUT),  # 硬编码引脚号，无属性访问
        mosi=Pin(mosi_pin, Pin.OUT),
        miso=None,
        polarity=0,
        phase=0,
        firstbit=SPI.MSB
    )

    # 3. 创建屏幕对象（和你的单屏代码一致）
    tft = gc9a01.GC9A01(
        spi=spi,
        dc=dc_pin,
        cs=cs_pin,
        reset=None,
        backlight=None,
        rotation=1
    )

    # 4. 开启背光+清屏（和你的单屏代码一致）
    backlight_pin.value(1)
    tft.fill(gc9a01.BLACK)
    time.sleep_ms(500)
    return tft

# -------------------------- 绘制函数（复用你的单屏逻辑） --------------------------
def draw_demo(tft, screen_num):
    """绘制演示内容，区分双屏"""
    tft.fill(gc9a01.WHITE)
    print(f"Display{screen_num} 填充白色，验证点亮！")
    time.sleep(1)

    if screen_num == 1:
        tft.fill(gc9a01.RED)
    else:
        tft.fill(gc9a01.BLUE)
    time.sleep(1)

    tft.fill(gc9a01.GREEN)
    time.sleep(1)
    tft.fill(gc9a01.YELLOW)
    time.sleep(1)

    tft.fill(gc9a01.BLACK)
    tft.line(0, 120, 239, 120, gc9a01.WHITE)
    tft.line(120, 0, 120, 239, gc9a01.WHITE)
    print(f"Display{screen_num} 绘制十字线，显示正常！")

# -------------------------- 主程序（复用你的单屏异常处理） --------------------------
if __name__ == "__main__":
    tft1 = None
    tft2 = None
    try:
        gc.collect()

        # 初始化Display1（传入硬编码引脚号）
        print("开始初始化Display1（强制硬件复位）...")
        tft1 = init_display(spi1, dc1_pin, cs1_pin, reset1_pin, backlight1_pin, sck1, mosi1)
        print("Display1 初始化完成！")

        # 初始化Display2（传入硬编码引脚号）
        print("开始初始化Display2（强制硬件复位）...")
        tft2 = init_display(spi2, dc2_pin, cs2_pin, reset2_pin, backlight2_pin, sck2, mosi2)
        print("Display2 初始化完成！")

        # 演示绘制
        draw_demo(tft1, 1)
        draw_demo(tft2, 2)
        print("双屏点亮演示完成！")

        while True:
            time.sleep(1)

    except Exception as e:
        print(f"运行出错：{e}")
        # 释放所有资源（和你的单屏逻辑一致）
        backlight1_pin.value(0)
        backlight2_pin.value(0)
        cs1_pin.value(1)
        cs2_pin.value(1)
        reset1_pin.value(1)
        reset2_pin.value(1)
        spi1.deinit()
        spi2.deinit()
        # machine_reset()  # 可选：重置开发板

