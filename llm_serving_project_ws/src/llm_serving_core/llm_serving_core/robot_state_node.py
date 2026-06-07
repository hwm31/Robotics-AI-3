#!/usr/bin/env python3
"""로봇 상태 관리 및 /robot_status 토픽 발행."""

import rclpy
from geometry_msgs.msg import Pose
from llm_serving_msgs.msg import RobotState
from nav_msgs.msg import Odometry
from rclpy.node import Node


class RobotStateNode(Node):
    def __init__(self):
        super().__init__('robot_state_node')
        self.declare_parameter('initial_battery', 100.0)

        self._battery = self.get_parameter('initial_battery').value
        self._loaded_items: list[str] = []
        self._pose = Pose()
        self._status = 'idle'

        self.state_pub = self.create_publisher(RobotState, 'robot_status', 10)
        self.create_subscription(Odometry, 'odom', self._on_odom, 10)
        self.timer = self.create_timer(1.0, self._publish_state)
        self.get_logger().info('Robot state node ready.')

    def _on_odom(self, msg: Odometry):
        self._pose = msg.pose.pose

    def _publish_state(self):
        msg = RobotState()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'map'
        msg.pose = self._pose
        msg.battery_percent = float(self._battery)
        msg.loaded_items = list(self._loaded_items)
        msg.status = self._status
        self.state_pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = RobotStateNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
