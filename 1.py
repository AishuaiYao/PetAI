import os




with open('data/log.txt', 'r', encoding='utf-8') as fr:
    lines = fr.readlines()

a = 0
b = 0
for line in lines:
    value = 0
    if "实际=" in line:
        value = line.split("实际=")[-1]
        a += float(value)
    if "播放音频块" in line:
        value = line.split(" 大小: ")[-1]
        b+= float(value)
print(a)
print(b)
print(a - b)








