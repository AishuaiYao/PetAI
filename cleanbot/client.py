import socket
import struct
import numpy as np
import cv2
import time
import os


class GrayscaleImageClient:
    def __init__(self, server_ip, server_port=5000):
        self.server_ip = server_ip
        self.server_port = server_port
        self.client_socket = None
        self.running = False
        self.frame_count = 0
        self.saved_count = 0

        # 性能统计
        self.start_time = None
        self.last_stat_time = None
        self.frames_in_last_second = 0
        self.total_bytes = 0

        # 灰度图的尺寸 (QVGA: 320x240)
        self.image_width = 320
        self.image_height = 240
        self.image_size = self.image_width * self.image_height  # 76800字节

    def connect(self):
        """连接到ESP32服务器"""
        print(f"尝试连接到 {self.server_ip}:{self.server_port}")

        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.client_socket.settimeout(5.0)
        self.client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

        try:
            self.client_socket.connect((self.server_ip, self.server_port))
            print("连接成功!")
            self.running = True
            return True
        except socket.error as e:
            print(f"连接失败: {e}")
            return False

    def receive_images(self, save_path="received_images", save_every_n=1):
        """
        接收灰度图像并保存为PNG
        Args:
            save_path: 保存路径
            save_every_n: 每N帧保存一次，1=保存每一帧
        """
        if not self.running:
            print("未连接到服务器")
            return

        # 创建保存目录
        os.makedirs(save_path, exist_ok=True)
        print(f"图像将保存到: {save_path}")

        print(f"开始接收灰度图像...")
        print(f"图像尺寸: {self.image_width}x{self.image_height}")
        print("按 Ctrl+C 停止接收\n")

        # 初始化统计
        self.start_time = time.time()
        self.last_stat_time = self.start_time
        self.frames_in_last_second = 0
        self.saved_count = 0

        try:
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

                self.frame_count += 1
                self.total_bytes += frame_size
                self.frames_in_last_second += 1

                # 每秒显示一次统计信息
                current_time = time.time()
                if current_time - self.last_stat_time >= 1.0:
                    fps = self.frames_in_last_second
                    data_rate = self.total_bytes / (current_time - self.start_time) / 1024

                    print(f"[{time.strftime('%H:%M:%S')}] "
                          f"接收: {self.frame_count}帧 | "
                          f"FPS: {fps:3d} | "
                          f"已保存: {self.saved_count}张 | "
                          f"速率: {data_rate:6.1f} KB/s")

                    self.last_stat_time = current_time
                    self.frames_in_last_second = 0

                # 保存PNG图像
                if self.frame_count % save_every_n == 0:
                    success = self._save_as_png(save_path, self.frame_count, image_data)
                    if success:
                        self.saved_count += 1

                        print(f"  -> 已保存 {self.saved_count} 张PNG图像")

        except KeyboardInterrupt:
            print("\n用户中断接收")
        except Exception as e:
            print(f"接收错误: {e}")
            import traceback
            traceback.print_exc()

        # 最终统计
        self._show_final_statistics()

    def _receive_bytes(self, num_bytes):
        """可靠地接收指定数量的字节"""
        data = b''
        remaining = num_bytes

        while remaining > 0:
            try:
                self.client_socket.settimeout(1.0)
                chunk = self.client_socket.recv(min(8192, remaining))

                if not chunk:
                    return None

                data += chunk
                remaining -= len(chunk)

            except socket.timeout:
                print(f"接收超时，剩余 {remaining} 字节")
                return None
            except socket.error as e:
                print(f"接收错误: {e}")
                return None

        return data

    def _save_as_png(self, save_path, frame_num, image_data):
        """保存为PNG图像"""
        try:
            # 转换为numpy数组
            if len(image_data) == self.image_size:
                gray_array = np.frombuffer(image_data, dtype=np.uint8)
                gray_array = gray_array.reshape((self.image_height, self.image_width))

                # 生成文件名
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                filename = f"{save_path}/frame_{frame_num:06d}_{timestamp}.png"

                # 保存为PNG
                cv2.imwrite(filename, gray_array)

                # 显示前几张的保存信息
                if frame_num <= 5:
                    file_size = os.path.getsize(filename)
                    print(f"  -> 保存第 {frame_num} 帧: {filename} ({file_size / 1024:.1f} KB)")

                return True
            else:
                print(f"第 {frame_num} 帧数据大小错误: {len(image_data)} != {self.image_size}")
                return False

        except Exception as e:
            print(f"保存第 {frame_num} 帧失败: {e}")
            return False

    def _show_final_statistics(self):
        """显示最终统计信息"""
        if not self.start_time:
            return

        total_time = time.time() - self.start_time

        print("\n" + "=" * 60)
        print("接收统计:")
        print(f"总接收时间: {total_time:.1f} 秒")
        print(f"总接收帧数: {self.frame_count} 帧")
        print(f"已保存图像: {self.saved_count} 张")

        if total_time > 0:
            print(f"平均帧率: {self.frame_count / total_time:.1f} FPS")
            print(f"总数据量: {self.total_bytes / 1024 / 1024:.2f} MB")
            print(f"平均数据速率: {self.total_bytes / total_time / 1024:.1f} KB/s")

        print("=" * 60)

    def cleanup(self):
        """清理资源"""
        self.running = False

        if self.client_socket:
            try:
                self.client_socket.close()
            except:
                pass

        print(f"客户端已停止")



def main():
    # 配置参数
    SERVER_IP = "192.168.4.1"  # ESP32 AP模式的默认IP
    SERVER_PORT = 5000
    SAVE_PATH = "GRAYSCALE_FRAME_QVGA"  # 图像保存路径

    print("灰度图像接收客户端")
    print(f"服务器: {SERVER_IP}:{SERVER_PORT}")
    print("-" * 40)

    # 创建客户端
    client = GrayscaleImageClient(SERVER_IP, SERVER_PORT)

    # 连接到服务器
    if client.connect():
        try:
            # 接收图像，参数说明：
            # save_path: 保存路径
            # save_every_n: 保存间隔，1=保存每一帧
            client.receive_images(
                save_path=SAVE_PATH,
                save_every_n=1  # 保存每一帧
            )
        except KeyboardInterrupt:
            print("\n程序被用户中断")
        except Exception as e:
            print(f"程序错误: {e}")
            import traceback
            traceback.print_exc()
        finally:
            client.cleanup()
    else:
        print("无法连接到服务器")

    print("程序结束")


if __name__ == '__main__':
    main()