import machine
import time
import math
from machine import I2S, Pin

# 引脚定义 - 使用安全GPIO
lrc_pin = Pin(10)  # 左右声道时钟 (I2S WS/FS)
sck_pin = Pin(9)  # 串行时钟 (I2S SCK/BCK) - 注意参数名是 sck
dout_pin = Pin(8)  # 数据输出 (I2S DOUT/SD)
sd_pin = Pin(21, Pin.OUT)  # 使能控制（GPIO21）
gain_pin = Pin(47, Pin.OUT)  # 增益控制（GPIO47）


def enable_amp(enable=True):
    """启用/禁用功放"""
    # MAX98375: SD=HIGH=工作, SD=LOW=关闭
    sd_pin.value(1 if enable else 0)
    print(f"Amplifier {'ENABLED' if enable else 'DISABLED'}")


def set_gain(high_gain=True):
    """设置增益"""
    # high_gain=True: 9dB, high_gain=False: 3dB
    gain_pin.value(1 if high_gain else 0)
    print(f"Gain set to {'9dB' if high_gain else '3dB'}")


def init_i2s():
    """初始化 I2S"""
    i2s = I2S(
        0,
        sck=sck_pin,  # 注意：这里参数名是 sck，不是 bck
        ws=lrc_pin,
        sd=dout_pin,
        mode=I2S.TX,
        bits=16,
        format=I2S.STEREO,
        rate=44100,
        ibuf=20000
    )
    return i2s


# 启用功放并设置初始增益
print("Initializing MAX98375...")
print("SD: GPIO21, GAIN: GPIO47")
enable_amp(True)  # 开启功放
set_gain(True)  # 设为高增益（9dB）
time.sleep(0.1)  # 等待稳定

# 初始化 I2S
i2s = init_i2s()

# 音频参数
SAMPLE_RATE = 44100
TONE_FREQ = 880  # 880Hz 高音，更容易听到
AMPLITUDE = 3000  # 音量
BUFFER_SIZE = 256  # 缓冲区大小

print("\n=== MAX98375 I2S Test ===")
print("Playing 880Hz tone...")
print("Press Ctrl+C to stop")

try:
    last_change = time.ticks_ms()
    last_status = time.ticks_ms()
    current_gain = True

    while True:
        # 生成正弦波
        buffer = bytearray(BUFFER_SIZE * 4)
        phase = 0.0
        phase_inc = 2 * math.pi * TONE_FREQ / SAMPLE_RATE

        for i in range(0, len(buffer), 4):
            sample = int(AMPLITUDE * math.sin(phase))

            # 16位立体声，小端序
            # 左声道
            buffer[i] = sample & 0xFF
            buffer[i + 1] = (sample >> 8) & 0xFF
            # 右声道
            buffer[i + 2] = sample & 0xFF
            buffer[i + 3] = (sample >> 8) & 0xFF

            phase += phase_inc
            if phase > 2 * math.pi:
                phase -= 2 * math.pi

        # 发送音频
        i2s.write(buffer)

        # 每3秒显示状态
        if time.ticks_ms() - last_status > 3000:
            print(f"Playing... {time.ticks_ms() // 1000}s elapsed")
            last_status = time.ticks_ms()

        # 每10秒切换增益
        if time.ticks_ms() - last_change > 10000:
            current_gain = not current_gain
            set_gain(current_gain)
            last_change = time.ticks_ms()

except KeyboardInterrupt:
    print("\nStopping test...")
finally:
    # 清理资源
    enable_amp(False)  # 关闭功放
    i2s.deinit()
    print("Amplifier disabled")
    print("Test finished")



# >>> %Run -c $EDITOR_CONTENT
#
# MPY: soft reboot
# Initializing MAX98375...
# SD: GPIO21, GAIN: GPIO47
# Amplifier ENABLED
# Gain set to 9dB
#
# === MAX98375 I2S Test ===
# Playing 880Hz tone...
# Press Ctrl+C to stop
# Playing... 120s elapsed
#
# Stopping test...
# Amplifier DISABLED
# Amplifier disabled
# Test finished
# >>>
