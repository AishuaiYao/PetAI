from machine import I2S, Pin
import struct

# 1. 硬件初始化（优化缓冲区+明确配置）
Pin(21, Pin.OUT).value(1)  # 启用功放
# 关键优化：ibuf大小设置为采样率的1/2（24000/2=12000），匹配16位数据特性
i2s = I2S(
    0,
    sck=Pin(9),
    ws=Pin(10),
    sd=Pin(8),
    mode=I2S.TX,
    bits=16,  # 匹配PCM：16位
    format=I2S.MONO,  # 匹配PCM：单声道
    rate=24000,  # 匹配PCM：24000Hz采样率
    ibuf=24000  # 优化缓冲区大小（16位数据建议采样率/2）
)


# 2. 优化的PCM播放函数（解决字节对齐+端序+缓冲区问题）
def play_raw_pcm(file_path):
    try:
        print("开始播放裸PCM音频（优化版）...")
        # 关键1：缓冲区大小必须是2的倍数（16位=2字节/样本）
        # 推荐用2048/4096，避免单字节残留导致的杂音
        buf_size = 4096
        buf = bytearray(buf_size)

        with open(file_path, "rb") as f:
            while True:
                # 读取数据（确保每次读取完整的样本数）
                num_read = f.readinto(buf)

                # 关键2：处理最后一段不完整的数据（必须是2字节的倍数）
                if num_read == 0:
                    break  # 播放完毕
                # if num_read % 2 != 0:
                #   num_read -= 1  # 舍弃最后一个不完整的字节

                # 关键4：阻塞式写入，确保数据完整发送
                written = 0
                while written < num_read:
                    written += i2s.write(buf[written:num_read])

        print("PCM音频播放完成！")
        # 清空缓冲区残留数据
        i2s.write(b'\x00\x00' * 100)

    except Exception as e:
        print(f"播放失败：{e}")
    finally:
        # 关闭功放、释放I2S
        Pin(21, Pin.OUT).value(0)
        i2s.deinit()


# 3. 执行播放（确保tts_raw.pcm已上传）
play_raw_pcm("tts_raw.pcm")
