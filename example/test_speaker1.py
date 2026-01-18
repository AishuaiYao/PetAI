from machine import I2S, Pin
import ubinascii

Pin(21, Pin.OUT).value(1)
i2s = I2S(
    0,
    sck=Pin(9),
    ws=Pin(10),
    sd=Pin(8),
    mode=I2S.TX,
    bits=16,
    format=I2S.MONO,
    rate=24000,
    ibuf=24000
)

def play_from_txt(txt_path):
    print(f"读取TXT文件: {txt_path}")
    print("开始播放音频...")

    with open(txt_path, 'r') as f:
        for line in f:
            base64_str = line.strip()
            if base64_str:
                audio_bytes = ubinascii.a2b_base64(base64_str)

                i2s.write(audio_bytes)

    print("播放完成！")
    i2s.write(b'\x00\x00' * 100)

play_from_txt("row_data.txt")
