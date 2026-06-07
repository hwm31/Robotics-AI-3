#!/usr/bin/env python3
"""LiDAR, watchdog, manual emergency stop based velocity safety filter."""

import json
import math
import time

import rclpy
from geometry_msgs.msg import Twist
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
from std_msgs.msg import String
from std_srvs.srv import SetBool


class SafetyControllerNode(Node):
    def __init__(self):
        super().__init__('safety_controller_node')
        self.declare_parameter('min_distance', 0.35)
        self.declare_parameter('clear_distance', 0.45)
        self.declare_parameter('front_angle_deg', 90.0)
        self.declare_parameter('scan_timeout_sec', 1.0)
        self.declare_parameter('cmd_timeout_sec', 0.8)
        self.declare_parameter('require_scan', True)
        self.declare_parameter('status_publish_period', 0.5)
        self.declare_parameter('stop_publish_period', 0.1)
        self.declare_parameter('scan_topic', 'scan')
        self.declare_parameter('cmd_vel_in', 'cmd_vel_raw')
        self.declare_parameter('cmd_vel_out', 'cmd_vel')
        self.declare_parameter('safety_status_topic', 'safety_status')
        self.declare_parameter('emergency_stop_service', 'emergency_stop')

        self._min_dist = float(self.get_parameter('min_distance').value)
        clear_distance = float(self.get_parameter('clear_distance').value)
        self._clear_dist = max(clear_distance, self._min_dist)
        self._front_angle = math.radians(
            float(self.get_parameter('front_angle_deg').value))
        self._scan_timeout = float(self.get_parameter('scan_timeout_sec').value)
        self._cmd_timeout = float(self.get_parameter('cmd_timeout_sec').value)
        self._require_scan = bool(self.get_parameter('require_scan').value)
        self._obstacle_detected = False
        self._manual_stop = False
        self._front_min_distance = math.inf
        self._last_scan_time: float | None = None
        self._last_cmd_time: float | None = None

        scan_topic = self.get_parameter('scan_topic').value
        cmd_in = self.get_parameter('cmd_vel_in').value
        cmd_out = self.get_parameter('cmd_vel_out').value
        status_topic = self.get_parameter('safety_status_topic').value
        stop_service = self.get_parameter('emergency_stop_service').value

        self.cmd_pub = self.create_publisher(Twist, cmd_out, 10)
        self.status_pub = self.create_publisher(String, status_topic, 10)
        self.create_subscription(LaserScan, scan_topic, self._on_scan, 10)
        self.create_subscription(Twist, cmd_in, self._on_cmd_vel, 10)
        self.create_service(SetBool, stop_service, self._handle_emergency_stop)

        self._last_cmd = Twist()
        self.create_timer(
            float(self.get_parameter('stop_publish_period').value),
            self._watchdog_timer,
        )
        self.create_timer(
            float(self.get_parameter('status_publish_period').value),
            self._publish_status,
        )
        self.get_logger().info(
            f'Safety controller active '
            f'(min_distance={self._min_dist}m, '
            f'clear_distance={self._clear_dist}m, '
            f'scan_timeout={self._scan_timeout}s)')

    def _on_scan(self, msg: LaserScan):
        half_angle = self._front_angle / 2.0
        valid = []
        self._last_scan_time = time.monotonic()

        for index, distance in enumerate(msg.ranges):
            angle = msg.angle_min + index * msg.angle_increment
            if abs(angle) > half_angle:
                continue
            if msg.range_min < distance < msg.range_max and math.isfinite(distance):
                valid.append(distance)

        was_blocked = self._obstacle_detected
        self._front_min_distance = min(valid) if valid else math.inf
        if self._front_min_distance < self._min_dist:
            self._obstacle_detected = True
        elif self._front_min_distance > self._clear_dist:
            self._obstacle_detected = False

        if self._should_block_motion():
            self._publish_stop()
            if not was_blocked:
                self.get_logger().warn('Obstacle detected - emergency stop!')
        elif was_blocked:
            self.get_logger().info('Obstacle cleared - resuming velocity pass-through.')

    def _on_cmd_vel(self, msg: Twist):
        self._last_cmd = msg
        self._last_cmd_time = time.monotonic()
        if self._should_block_motion():
            self._publish_stop()
        else:
            self.cmd_pub.publish(msg)

    def _handle_emergency_stop(self, request, response):
        self._manual_stop = bool(request.data)
        if self._manual_stop:
            self._publish_stop()
            message = 'Manual emergency stop engaged.'
            self.get_logger().warn(message)
        else:
            message = 'Manual emergency stop released.'
            self.get_logger().info(message)

        response.success = True
        response.message = message
        self._publish_status()
        return response

    def _watchdog_timer(self):
        if self._should_block_motion() or self._is_cmd_stale():
            self._publish_stop()

    def _publish_stop(self):
        self.cmd_pub.publish(Twist())

    def _should_block_motion(self) -> bool:
        return (
            self._manual_stop
            or self._obstacle_detected
            or self._is_scan_stale()
        )

    def _is_scan_stale(self) -> bool:
        if not self._require_scan:
            return False
        if self._last_scan_time is None:
            return True
        return (time.monotonic() - self._last_scan_time) > self._scan_timeout

    def _is_cmd_stale(self) -> bool:
        if self._last_cmd_time is None:
            return False
        if not self._is_motion_command(self._last_cmd):
            return False
        return (time.monotonic() - self._last_cmd_time) > self._cmd_timeout

    def _is_motion_command(self, msg: Twist) -> bool:
        return any([
            abs(msg.linear.x) > 1.0e-4,
            abs(msg.linear.y) > 1.0e-4,
            abs(msg.linear.z) > 1.0e-4,
            abs(msg.angular.x) > 1.0e-4,
            abs(msg.angular.y) > 1.0e-4,
            abs(msg.angular.z) > 1.0e-4,
        ])

    def _publish_status(self):
        reasons = []
        if self._manual_stop:
            reasons.append('manual_emergency_stop')
        if self._obstacle_detected:
            reasons.append('obstacle_too_close')
        if self._is_scan_stale():
            reasons.append('scan_timeout')
        if self._is_cmd_stale():
            reasons.append('cmd_timeout')

        status = {
            'safe': not reasons,
            'reason': reasons or ['ok'],
            'manual_stop': self._manual_stop,
            'obstacle_detected': self._obstacle_detected,
            'scan_timeout': self._is_scan_stale(),
            'cmd_timeout': self._is_cmd_stale(),
            'front_min_distance': (
                None
                if math.isinf(self._front_min_distance)
                else round(self._front_min_distance, 3)
            ),
            'min_distance': self._min_dist,
            'clear_distance': self._clear_dist,
        }

        msg = String()
        msg.data = json.dumps(status, ensure_ascii=False)
        self.status_pub.publish(msg)


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
