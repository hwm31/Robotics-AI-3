#!/usr/bin/env python3

import json

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class GreetingNode(Node):

    def __init__(self):
        super().__init__("greeting_node")

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

        # 추가: 실제 이동 노드로 이동 목표 전달
        self.move_goal_pub = self.create_publisher(
            String,
            "greeting_move_goal",
            10
        )

        self.waiting_for_llm = False
        self.waiting_for_table = False

        self.get_logger().info("Greeting Node Started")

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
            f"Sent guest command to seat manager: {guest_msg.data}"
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
        x = data.get("x")
        y = data.get("y")
        yaw = data.get("yaw", 0.0)

        if table_id is None:
            self.get_logger().error("No table id in assignment result")
            self.waiting_for_table = False
            return

        print(f"Robot: Please follow me to Table {table_id}.")

        if x is None or y is None:
            self.get_logger().warn(
                "Table coordinates not received. Cannot publish move goal."
            )
            self.waiting_for_table = False
            return

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

    def run(self):
        while rclpy.ok():
            cmd = input("\n[N] New Customer | [Q] Quit : ").lower()

            if cmd == "q":
                break

            if cmd == "n":
                self.process_customer()

            rclpy.spin_once(self, timeout_sec=0.1)


def main(args=None):
    rclpy.init(args=args)

    node = GreetingNode()

    try:
        node.run()
    except KeyboardInterrupt:
        pass

    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()