#!/usr/bin/env python3
"""LiDAR 기반 충돌 임박 시 비상 정지."""

import math

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from sensor_msgs.msg import LaserScan


class SafetyControllerNode(Node):
    def __init__(self):
        super().__init__('safety_controller_node')
        self.declare_parameter('min_distance', 0.35)
        self.declare_parameter('front_angle_deg', 90.0)
        self.declare_parameter('scan_topic', 'scan')
        self.declare_parameter('cmd_vel_in', 'cmd_vel_raw')
        self.declare_parameter('cmd_vel_out', 'cmd_vel')

        self._min_dist = self.get_parameter('min_distance').value
        self._front_angle = math.radians(
            float(self.get_parameter('front_angle_deg').value))
        self._obstacle_detected = False

        scan_topic = self.get_parameter('scan_topic').value
        cmd_in = self.get_parameter('cmd_vel_in').value
        cmd_out = self.get_parameter('cmd_vel_out').value

        self.cmd_pub = self.create_publisher(Twist, cmd_out, 10)
        self.create_subscription(LaserScan, scan_topic, self._on_scan, 10)
        self.create_subscription(Twist, cmd_in, self._on_cmd_vel, 10)

        self._last_cmd = Twist()
        self.get_logger().info(
            f'Safety controller active (min_distance={self._min_dist}m)')

    def _on_scan(self, msg: LaserScan):
        half_angle = self._front_angle / 2.0
        valid = []

        for index, distance in enumerate(msg.ranges):
            angle = msg.angle_min + index * msg.angle_increment
            if abs(angle) > half_angle:
                continue
            if msg.range_min < distance < msg.range_max and math.isfinite(distance):
                valid.append(distance)

        was_blocked = self._obstacle_detected
        self._obstacle_detected = bool(valid) and min(valid) < self._min_dist

        if self._obstacle_detected:
            stop = Twist()
            self.cmd_pub.publish(stop)
            if not was_blocked:
                self.get_logger().warn('Obstacle detected - emergency stop!')
        elif was_blocked:
            self.get_logger().info('Obstacle cleared - resuming velocity pass-through.')

    def _on_cmd_vel(self, msg: Twist):
        self._last_cmd = msg
        if not self._obstacle_detected:
            self.cmd_pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = SafetyControllerNode()
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
