import socket
import struct
import numpy as np
import cv2
import time
import sys


class GrayscaleImageClient:
    def __init__(self, server_ip, server_port=5000):
        self.server_ip = server_ip
        self.server_port = server_port
        self.client_socket = None
        self.running = False
        self.frame_count = 0

        # 灰度图的尺寸 (QVGA: 320x240)
        self.image_width = 320
        self.image_height = 240
        self.image_size = self.image_width * self.image_height  # 灰度图每个像素1字节

    def connect(self):
        """连接到ESP32服务器"""
        print(f"尝试连接到 {self.server_ip}:{self.server_port}")

        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.client_socket.settimeout(5)  # 设置连接超时

        try:
            self.client_socket.connect((self.server_ip, self.server_port))
            print("连接成功!")
            self.running = True
            return True
        except socket.error as e:
            print(f"连接失败: {e}")
            return False

    def receive_images(self, save_path=None):
        """接收并显示/保存灰度图像"""
        if not self.running:
            print("未连接到服务器")
            return

        print("开始接收灰度图像...")
        print(f"图像尺寸: {self.image_width}x{self.image_height}")

        while self.running:
            # 1. 接收帧大小 (4字节)
            header_data = self._receive_bytes(4)
            if not header_data:
                print("连接断开")
                break

            # 解析帧大小
            frame_size = struct.unpack('>I', header_data)[0]

            # 2. 接收图像数据
            image_data = self._receive_bytes(frame_size)
            if not image_data:
                print("图像数据接收不完整")
                break

            if len(image_data) != frame_size:
                print(f"数据长度不匹配: 期望 {frame_size}, 实际 {len(image_data)}")
                continue

            # 3. 转换为numpy数组 (灰度图)
            # 灰度图是单通道，每个像素1字节
            if len(image_data) == self.image_size:
                # 转换为numpy数组 (单通道)
                gray_array = np.frombuffer(image_data, dtype=np.uint8)

                self.frame_count += 1
                print(f"帧 {self.frame_count}: 接收到 {frame_size} 字节 (灰度图)")
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                filename = f"{save_path}/frame_{self.frame_count}_{timestamp}.png"
                cv2.imwrite(filename, gray_array)
                print(f"图像已保存: {filename}")
            else:
                print(f"数据大小不匹配: 期望 {self.image_size}, 实际 {len(image_data)}")


    def _receive_bytes(self, num_bytes):
        """可靠地接收指定数量的字节"""
        data = b''
        remaining = num_bytes

        while remaining > 0:
            try:
                chunk = self.client_socket.recv(min(4096, remaining))
                if not chunk:
                    return None
                data += chunk
                remaining -= len(chunk)
            except socket.timeout:
                continue
            except socket.error:
                return None

        return data

    def cleanup(self):
        """清理资源"""
        if self.client_socket:
            self.client_socket.close()
        self.running = False
        print(f"客户端已停止，总共接收 {self.frame_count} 帧")


def main():
    # 配置参数
    SERVER_IP = "192.168.4.1"  # ESP32 AP模式的默认IP
    SERVER_PORT = 5000
    SAVE_PATH = "received_images"  # 图像保存路径

    # 创建保存目录
    import os
    if not os.path.exists(SAVE_PATH):
        os.makedirs(SAVE_PATH)
        print(f"创建保存目录: {SAVE_PATH}")

    # 创建客户端
    client = GrayscaleImageClient(SERVER_IP, SERVER_PORT)

    # 连接到服务器
    if client.connect():

        client.receive_images(save_path=SAVE_PATH)

    else:
        print("无法连接到服务器")

    print("程序结束")


if __name__ == '__main__':
    main()