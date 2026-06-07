#!/usr/bin/env python3

import threading
import json
import os
import re

import rclpy
import yaml
from ament_index_python.packages import get_package_share_directory
from rclpy.node import Node
from std_msgs.msg import String


class GreetingNode(Node):

    def __init__(self):
        super().__init__("greeting_node")

        self.table_coordinates = self.load_table_coordinates()

        self.user_command_pub = self.create_publisher(
            String,
            "user_command",
            10
        )

        self.llm_task_sub = self.create_subscription(
            String,
            "llm_task",
            self.llm_task_callback,
            10
        )

        self.guest_command_pub = self.create_publisher(
            String,
            "guest_command",
            10
        )

        self.table_assignment_sub = self.create_subscription(
            String,
            "table_assignment",
            self.table_assignment_callback,
            10
        )

        self.move_goal_pub = self.create_publisher(
            String,
            "greeting_move_goal",
            10
        )

        self.waiting_for_llm = False
        self.waiting_for_table = False

        self.get_logger().info("Greeting Node Started")

    def load_table_coordinates(self):
        share_dir = get_package_share_directory("llm_serving_core")
        map_path = os.path.join(share_dir, "config", "restaurant_map.yaml")

        with open(map_path, "r", encoding="utf-8") as f:
            restaurant_map = yaml.safe_load(f)

        table_coordinates = {}

        for table in restaurant_map.get("tables", []):
            table_id = table.get("id", table.get("table_id", table.get("number")))

            if table_id is None:
                table_id = table.get("name")

            if isinstance(table_id, str):
                match = re.search(r'\d+', table_id)
                if match is None:
                    self.get_logger().warn(f"Cannot find table number from: {table_id}")
                    continue
                table_id = int(match.group())
            else:
                table_id = int(table_id)

            table_coordinates[table_id] = {
                "x": float(table["x"]),
                "y": float(table["y"]),
                "yaw": float(table.get("yaw", 0.0)),
            }

        self.get_logger().info(
            f"Loaded {len(table_coordinates)} table coordinates from restaurant_map.yaml"
        )

        return table_coordinates

    def llm_task_callback(self, msg: String):
        if not self.waiting_for_llm:
            return

        try:
            task = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().error("Invalid LLM JSON")
            self.waiting_for_llm = False
            return

        people = task.get("people")

        if people is None:
            print("Robot: Sorry, how many people?")
            self.waiting_for_llm = False
            return

        guest_msg = String()
        guest_msg.data = json.dumps(
            {
                "event": "arrive",
                "count": int(people)
            },
            ensure_ascii=False
        )

        self.guest_command_pub.publish(guest_msg)

        self.waiting_for_llm = False
        self.waiting_for_table = True

        self.get_logger().info(
            f"Sent guest command to table_state_node: {guest_msg.data}"
        )

    def table_assignment_callback(self, msg: String):
        if not self.waiting_for_table:
            return

        try:
            data = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().error("Invalid table assignment JSON")
            self.waiting_for_table = False
            return

        if data.get("success") is False:
            reason = data.get("reason") or data.get("message") or "no available table"
            print(f"Robot: Sorry, {reason}.")
            self.waiting_for_table = False
            return

        table_id = data.get("table_id") or data.get("table")

        if table_id is None:
            self.get_logger().error("No table id in assignment result")
            self.waiting_for_table = False
            return

        try:
            table_id = int(table_id)
        except ValueError:
            self.get_logger().error(f"Invalid table id: {table_id}")
            self.waiting_for_table = False
            return

        if table_id not in self.table_coordinates:
            self.get_logger().error(f"No coordinates for table {table_id}")
            self.waiting_for_table = False
            return

        coord = self.table_coordinates[table_id]

        x = coord["x"]
        y = coord["y"]
        yaw = coord["yaw"]

        print(f"Robot: Please follow me to Table {table_id}.")

        move_msg = String()
        move_msg.data = json.dumps(
            {
                "task": "guide_customer",
                "table_id": table_id,
                "x": float(x),
                "y": float(y),
                "yaw": float(yaw)
            },
            ensure_ascii=False
        )

        self.move_goal_pub.publish(move_msg)

        self.get_logger().info(
            f"Published greeting move goal: {move_msg.data}"
        )

        self.waiting_for_table = False

    def process_customer(self):
        print("\n=== New Customer Arrived ===")

        customer_text = input(
            "Robot: Hello! How many people?\nCustomer: "
        )

        if not customer_text.strip():
            print("Robot: Sorry, please say that again.")
            return

        msg = String()
        msg.data = customer_text

        self.user_command_pub.publish(msg)
        self.waiting_for_llm = True

        self.get_logger().info(
            f"Sent customer sentence to LLM: {customer_text}"
        )




def main(args=None):
    rclpy.init(args=args)

    node = GreetingNode()

    spin_thread = threading.Thread(
        target=rclpy.spin,
        args=(node,),
        daemon=True
    )
    spin_thread.start()

    try:
        while rclpy.ok():
            cmd = input("\n[N] New Customer | [Q] Quit : ").lower()

            if cmd == "q":
                break

            if cmd == "n":
                node.process_customer()

    except KeyboardInterrupt:
        pass

    node.destroy_node()
    if rclpy.ok():
        rclpy.shutdown()


if __name__ == "__main__":
    main()
