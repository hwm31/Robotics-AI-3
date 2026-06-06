#!/usr/bin/env python3

import json
import math

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from geometry_msgs.msg import PoseStamped
from nav2_simple_commander.robot_navigator import BasicNavigator


class GreetingToTableNode(Node):

    def __init__(self):
        super().__init__("greeting_to_table_node")

        self.navigator = BasicNavigator()

        self.sub = self.create_subscription(
            String,
            "greeting_move_goal",
            self.move_goal_callback,
            10
        )

        self.get_logger().info("Greeting To Table Node Started")
        self.get_logger().info("Waiting for greeting_move_goal...")

    def move_goal_callback(self, msg: String):
        try:
            data = json.loads(msg.data)

            table_num = int(data["table_id"])
            x = float(data["x"])
            y = float(data["y"])
            yaw = float(data.get("yaw", 0.0))

            self.get_logger().info(
                f"Received move goal: table={table_num}, x={x}, y={y}, yaw={yaw}"
            )

            goal_pose = self.make_goal_pose(x, y, yaw)

            self.get_logger().info(f"Sending Nav2 goal to Table {table_num}")
            self.navigator.goToPose(goal_pose)

        except KeyError as e:
            self.get_logger().error(f"Missing key in greeting_move_goal: {e}")
            self.get_logger().error(f"Received data: {msg.data}")

        except json.JSONDecodeError:
            self.get_logger().error("Failed to decode greeting_move_goal JSON")
            self.get_logger().error(f"Received data: {msg.data}")

        except Exception as e:
            self.get_logger().error(f"Error while processing move goal: {e}")

    def make_goal_pose(self, x, y, yaw):
        goal_pose = PoseStamped()

        goal_pose.header.frame_id = "map"
        goal_pose.header.stamp = self.get_clock().now().to_msg()

        goal_pose.pose.position.x = x
        goal_pose.pose.position.y = y
        goal_pose.pose.position.z = 0.0

        goal_pose.pose.orientation.z = math.sin(yaw / 2.0)
        goal_pose.pose.orientation.w = math.cos(yaw / 2.0)

        return goal_pose


def main(args=None):
    rclpy.init(args=args)

    node = GreetingToTableNode()

    try:
        rclpy.spin(node)

    except KeyboardInterrupt:
        node.get_logger().info("Greeting To Table Node stopped by user")

    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()