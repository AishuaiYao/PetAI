import requests
import json
import pyaudio
import time
import base64
import numpy as np
import os
from typing import Optional, Dict, Any


class TTSService:
    def __init__(self, api_key: str, voice: str = "Cherry", language: str = "Chinese"):
        self.api_base_url = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
        self.api_key = api_key
        self.voice = voice
        self.language = language
        self.stream_data = {}

        # 音频播放初始化
        self.p = pyaudio.PyAudio()
        self.stream = self.p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=24000,
            output=True
        )

    def _create_headers(self) -> Dict[str, str]:
        """创建请求头"""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-DashScope-SSE": "enable"
        }

    def _create_payload(self, text: str) -> Dict[str, Any]:
        """创建请求负载"""
        return {
            "model": "qwen3-tts-flash",
            "input": {"text": text},
            "parameters": {
                "voice": self.voice,
                "language_type": self.language
            }
        }

    def _process_audio_chunk(self, audio_data: str, count: int) -> None:
        """处理并播放音频数据块"""
        wav_bytes = base64.b64decode(audio_data)
        audio_np = np.frombuffer(wav_bytes, dtype=np.int16)
        audio_bytes = audio_np.tobytes()
        self.stream.write(audio_bytes)

        self.stream_data[count]["audio_data"] = audio_data

        print(f"✓ 播放音频块，大小: {len(audio_np)} samples")

    def _parse_sse_line(self, line_str: str) -> Optional[Dict[str, Any]]:
        """解析SSE数据行"""
        if not line_str.startswith('data:'):
            return None

        json_str = line_str[5:]
        if json_str == '[DONE]':
            print("收到结束标记")
            return {"type": "done"}

        try:
            return {"type": "data", "data": json.loads(json_str)}
        except json.JSONDecodeError:
            print(f"JSON解析错误，数据: {json_str[:200]}...")
            return None

    def _handle_chunk_data(self, chunk: Dict[str, Any], count: int) -> bool:
        """处理数据块，返回是否继续处理"""
        if "output" not in chunk:
            return True

        # 检查是否完成
        if chunk["output"].get("finish_reason") == "stop":
            print("✓ 流式传输完成")
            return False

        # 处理音频数据
        audio_info = chunk["output"].get("audio", {})
        if "data" in audio_info:
            self._process_audio_chunk(audio_info["data"], count)

        return True

    def synthesize_speech(self, text: str) -> bool:
        """主函数：合成并播放语音"""
        print(f"正在请求 URL: {self.api_base_url}")

        try:
            response = requests.post(
                self.api_base_url,
                headers=self._create_headers(),
                json=self._create_payload(text),
                stream=True,
                timeout=30
            )

            print(f"响应状态码: {response.status_code}")

            if response.status_code != 200:
                self._handle_error_response(response)
                return False

            print("请求成功，开始接收音频流...")
            return self._process_stream_response(response)

        except requests.exceptions.RequestException as e:
            print(f"请求异常: {e}")
            return False
        except Exception as e:
            print(f"其他异常: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _handle_error_response(self, response: requests.Response) -> None:
        """处理错误响应"""
        try:
            error_data = response.json()
            print(f"错误响应: {json.dumps(error_data, ensure_ascii=False, indent=2)}")
        except:
            print(f"响应内容: {response.text}")

    def _process_stream_response(self, response: requests.Response) -> bool:
        """处理流式响应"""
        self.stream_data = {}
        count = 0
        
        for line in response.iter_lines():
            if not line:
                continue

            line_str = line.decode('utf-8')
            parsed = self._parse_sse_line(line_str)
            if parsed is None:
                continue

            count += 1
            self.stream_data[count] = {
                "line": line_str,
                "parsed": parsed
            }

            if parsed["type"] == "done":
                break

            if not self._handle_chunk_data(parsed["data"], count):
                break

        print(f"共获取 {count} 条数据")
        return True

    def _save_stream_data(self) -> None:
        """保存流数据到本地"""
        filepath = "../../data/tts_stream_data.json"
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.stream_data, f, ensure_ascii=False, indent=2)
        print(f"数据已保存到 {filepath}")

    def cleanup(self) -> None:
        """清理资源"""
        time.sleep(1.0)  # 等待音频播放完成
        self.stream.stop_stream()
        self.stream.close()
        self.p.terminate()
        
        self._save_stream_data()
        print("音频播放完成，资源已清理")


def main():
    """主程序入口"""
    text = "你好作者你好啊，现在是tts测试"
    api_key = 'sk-943f95da67d04893b70c02be400e2935'

    tts_service = TTSService(api_key=api_key)

    try:
        success = tts_service.synthesize_speech(text)
        if not success:
            print("语音合成失败")
    finally:
        tts_service.cleanup()


if __name__ == "__main__":
    main()