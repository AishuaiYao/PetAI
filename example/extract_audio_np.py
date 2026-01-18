import json
import base64

with open("../data/tts_stream_data.json", 'r', encoding='utf-8') as f:
    data = json.load(f)

with open("../data/row_data.txt", 'w', encoding='utf-8') as f:
    for key in sorted(data.keys(), key=int):
        chunk = data[key]
        if 'audio_data' in chunk:
            audio_data =chunk['audio_data']
            f.write(audio_data + '\n')

print("已保存到 data/row_data.txt")
