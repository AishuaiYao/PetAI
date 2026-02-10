import socket
import time
import struct
from PIL import Image
import io
import os
from datetime import datetime


class ESP32CameraClient:
    def __init__(self, host='192.168.4.1', port=5000, save_dir='captured_images'):
        """
        初始化ESP32摄像头客户端

        参数:
            host: ESP32的IP地址 (AP模式下通常是192.168.4.1)
            port: 端口号
            save_dir: 图像保存目录
        """
        self.host = host
        self.port = port
        self.save_dir = save_dir
        self.client_socket = None
        self.received_count = 0

        # 创建保存目录
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
            print(f"创建保存目录: {save_dir}")

    def connect(self):
        """连接到ESP32服务器"""
        print(f"正在连接到 {self.host}:{self.port}...")
        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.client_socket.settimeout(10)  # 设置连接超时
        self.client_socket.connect((self.host, self.port))
        self.client_socket.settimeout(5.0)  # 设置接收超时
        print("连接成功!")
        print("开始接收图像...")

    def receive_images(self, max_frames=None, auto_reconnect=True):
        """
        接收并保存图像

        参数:
            max_frames: 最大接收帧数，None表示无限制
            auto_reconnect: 连接断开时是否自动重连
        """
        while True:
            try:
                if self.client_socket is None:
                    if auto_reconnect:
                        print("尝试重新连接...")
                        self.connect()
                    else:
                        break

                # 接收帧大小 (4字节)
                header = self.receive_all(4)
                if not header or len(header) != 4:
                    print("连接异常或数据不完整")
                    if auto_reconnect:
                        self.disconnect()
                        continue
                    else:
                        break

                frame_size = struct.unpack('>I', header)[0]
                print(f"正在接收帧 {self.received_count + 1}, 大小: {frame_size} 字节")

                # 接收图像数据
                image_data = self.receive_all(frame_size)
                if not image_data:
                    print("图像数据接收失败")
                    continue

                # 保存图像
                self.save_image(image_data)
                self.received_count += 1

                # 检查是否达到最大帧数
                if max_frames is not None and self.received_count >= max_frames:
                    print(f"已达到最大帧数 {max_frames}")
                    break

            except socket.timeout:
                print("接收超时，继续等待...")
                continue
            except ConnectionError as e:
                print(f"连接错误: {e}")
                if auto_reconnect:
                    self.disconnect()
                    time.sleep(2)
                    continue
                else:
                    break
            except KeyboardInterrupt:
                print("\n用户中断接收")
                break
            except Exception as e:
                print(f"接收错误: {e}")
                continue

    def receive_all(self, size):
        """接收指定大小的数据"""
        data = bytearray()
        while len(data) < size:
            try:
                chunk = self.client_socket.recv(min(4096, size - len(data)))
                if not chunk:
                    return None
                data.extend(chunk)
            except socket.timeout:
                continue
        return bytes(data)

    def save_image(self, image_data):
        """
        保存图像为PNG格式

        参数:
            image_data: 图像字节数据
        """
        try:
            # 生成文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"frame_{self.received_count:04d}_{timestamp}.png"
            filepath = os.path.join(self.save_dir, filename)

            # 处理JPEG并保存为PNG
            try:
                image = Image.open(io.BytesIO(image_data))

                # 转换为PNG
                if image.mode != 'RGB':
                    image = image.convert('RGB')

                image.save(filepath, 'PNG', optimize=True)
                print(f"✓ 已保存: {filename} ({image.size[0]}x{image.size[1]})")

            except Exception as e:
                print(f"图像处理失败，保存为JPEG: {e}")
                # 如果PIL无法处理，直接保存为JPEG
                filepath_jpg = filepath.replace('.png', '.jpg')
                with open(filepath_jpg, 'wb') as f:
                    f.write(image_data)
                print(f"✓ 已保存原始JPEG: {filename}")

        except Exception as e:
            print(f"保存图像错误: {e}")

    def disconnect(self):
        """断开连接"""
        if self.client_socket:
            self.client_socket.close()
            self.client_socket = None
        print(f"已断开连接，总共接收 {self.received_count} 帧")

    def run(self, max_frames=None):
        """运行客户端"""
        try:
            self.connect()
            self.receive_images(max_frames=max_frames)
        except KeyboardInterrupt:
            print("\n程序被用户中断")
        except Exception as e:
            print(f"程序错误: {e}")
        finally:
            self.disconnect()


def main():
    """主函数"""
    print("=" * 50)
    print("ESP32摄像头图像接收客户端")
    print("=" * 50)

    # 配置参数
    ESP32_IP = "192.168.4.1"  # ESP32在AP模式下的默认IP
    PORT = 5000
    SAVE_DIR = "captured_images"
    MAX_FRAMES = None  # None表示无限制

    # 创建客户端并运行
    client = ESP32CameraClient(
        host=ESP32_IP,
        port=PORT,
        save_dir=SAVE_DIR
    )

    print(f"目标设备: {ESP32_IP}:{PORT}")
    print(f"保存目录: {SAVE_DIR}")
    print("按 Ctrl+C 停止接收\n")

    client.run(max_frames=MAX_FRAMES)


if __name__ == '__main__':
    # 注意：需要在代码顶部定义AP_SSID，或者在main函数中定义
    AP_SSID = "ESP32-CAM-AP"
    main()