# 导入必要模块
from machine import Pin, SPI, reset as machine_reset
import gc9a01
import time
import gc

# -------------------------- 严格匹配你的引脚配置 --------------------------
# 先手动初始化所有引脚（避免状态残留）
dc_pin = Pin(41, Pin.OUT)  # 显式定义为输出模式
cs_pin = Pin(40, Pin.OUT)  # 显式定义为输出模式
reset_pin = Pin(42, Pin.OUT)  # 显式定义为输出模式
backlight_pin = Pin(39, Pin.OUT)  # 显式定义为输出模式

# 强制初始化引脚默认状态
cs_pin.value(1)  # CS拉高（未选中）
dc_pin.value(0)  # DC拉低（默认命令模式）
reset_pin.value(1)  # RST拉高（正常状态）
backlight_pin.value(0)  # 先关闭背光

# SPI总线配置（添加参数避免总线残留）
spi = SPI(
    2,
    baudrate=20000000,
    sck=Pin(1, Pin.OUT),  # 显式定义SCK为输出
    mosi=Pin(2, Pin.OUT),  # 显式定义MOSI为输出
    miso=None,
    polarity=0,  # 固定SPI极性
    phase=0,  # 固定SPI相位
    firstbit=SPI.MSB  # 固定高位优先
)


# -------------------------- 增强版初始化（强制硬件复位） --------------------------
def init_display():
    """初始化GC9A01显示屏（包含硬件复位，解决状态残留）"""
    # 1. 强制硬件复位屏幕（关键！解决状态残留）
    reset_pin.value(0)  # RST拉低（复位）
    time.sleep_ms(100)  # 保持复位100ms
    reset_pin.value(1)  # RST拉高（退出复位）
    time.sleep_ms(200)  # 等待屏幕上电

    # 2. 重新初始化SPI总线（释放残留数据）
    spi.deinit()  # 先关闭SPI
    time.sleep_ms(50)
    spi.init(  # 重新初始化SPI
        baudrate=20000000,
        sck=Pin(1, Pin.OUT),
        mosi=Pin(2, Pin.OUT),
        miso=None,
        polarity=0,
        phase=0,
        firstbit=SPI.MSB
    )

    # 3. 创建显示屏对象
    tft = gc9a01.GC9A01(
        spi=spi,
        dc=dc_pin,
        cs=cs_pin,
        reset=None,  # 已手动复位，禁用库内复位
        backlight=None,  # 手动控制背光，避免库内干扰
        rotation=1
    )

    # 4. 手动开启背光（确保每次运行都亮）
    backlight_pin.value(1)

    # 5. 清屏（强制刷新屏幕）
    tft.fill(gc9a01.BLACK)
    time.sleep_ms(500)
    return tft


# -------------------------- 绘制演示内容 --------------------------
def draw_demo(tft):
    """绘制简单图形，验证屏幕点亮"""
    # 1. 填充全屏白色
    tft.fill(gc9a01.WHITE)
    print("屏幕填充白色，验证点亮！")
    time.sleep(1)

    # 2. 填充红色
    tft.fill(gc9a01.RED)
    time.sleep(1)

    # 3. 填充绿色
    tft.fill(gc9a01.GREEN)
    time.sleep(1)

    # 4. 填充蓝色
    tft.fill(gc9a01.BLUE)
    time.sleep(1)

    # 5. 清屏并绘制十字线
    tft.fill(gc9a01.BLACK)
    tft.line(0, 120, 239, 120, gc9a01.WHITE)
    tft.line(120, 0, 120, 239, gc9a01.WHITE)
    print("绘制十字线，显示正常！")


# -------------------------- 主程序（添加异常处理和资源释放） --------------------------
if __name__ == "__main__":
    try:
        # 清理内存（避免资源占用）
        gc.collect()

        # 初始化显示屏
        print("开始初始化显示屏（强制硬件复位）...")
        tft = init_display()
        print("显示屏初始化完成！")

        # 执行点亮演示
        draw_demo(tft)
        print("点亮演示完成！")

        # 保持运行
        while True:
            time.sleep(1)

    except Exception as e:
        print(f"运行出错：{e}")
        # 出错时强制关闭所有引脚
        backlight_pin.value(0)
        cs_pin.value(1)
        reset_pin.value(1)
        spi.deinit()
        # 可选：极端情况重置开发板
        # machine_reset()