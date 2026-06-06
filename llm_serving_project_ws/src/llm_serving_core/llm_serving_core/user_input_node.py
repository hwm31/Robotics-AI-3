#!/usr/bin/env python3
"""자연어 명령 입력 → /user_command 토픽 발행."""

import rclpy
from llm_serving_core.guest_command_parser import parse_guest_command
from rclpy.node import Node
from std_msgs.msg import String


class UserInputNode(Node):
    def __init__(self):
        super().__init__('user_input_node')
        self.publisher_ = self.create_publisher(String, 'user_command', 10)
        self.guest_pub = self.create_publisher(String, 'guest_command', 10)
        self.get_logger().info(
            'User input node ready. Commands: serve orders or guest events '
            '(e.g. "손님 2명 입장", "1번 테이블 퇴장", "테이블 상태"). Ctrl+C to quit.')

        self.timer = self.create_timer(0.1, self._poll_input)

    def _poll_input(self):
        try:
            import sys
            import select
            if select.select([sys.stdin], [], [], 0)[0]:
                line = sys.stdin.readline().strip()
                if line:
                    guest_json = parse_guest_command(line)
                    if guest_json is not None:
                        msg = String()
                        msg.data = guest_json
                        self.guest_pub.publish(msg)
                        self.get_logger().info(f'Published guest_command: {guest_json}')
                    else:
                        msg = String()
                        msg.data = line
                        self.publisher_.publish(msg)
                        self.get_logger().info(f'Published command: {line}')
        except Exception:
            pass


def main(args=None):
    rclpy.init(args=args)
    node = UserInputNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
