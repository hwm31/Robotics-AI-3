#!/usr/bin/env python3

"""
주문 큐 변환 노드 — LLM 주문 계획 검증, 주문 단위 분리, 주문 큐 토픽 발행.

기능:
- /order_plan 토픽 수신
- LLM이 생성한 JSON 주문 계획 검증
- 여러 메뉴 주문을 개별 주문으로 분리
- 각 주문에 order_id 부여
- /order_queue 토픽 발행
"""

import json
import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class OrderQueueNode(Node):
    def __init__(self):
        super().__init__('order_queue_node')

        self.order_plan_sub = self.create_subscription(
            String,
            '/order_plan',
            self.order_plan_callback,
            10
        )

        self.order_pub = self.create_publisher(
            String,
            '/order_queue',
            10
        )

        self.order_id = 1
        self.allowed_tables = [f"table_{i}" for i in range(1, 13)]
        self.allowed_items = ["water", "coffee", "steak", "pasta"]

        self.get_logger().info("=== order_queue_node 시작 ===")

    def order_plan_callback(self, msg):
        self.get_logger().info(f"/order_plan 수신: {msg.data}")

        try:
            plan = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().error("order_plan JSON 파싱 실패")
            return

        if not self.validate_plan(plan):
            self.get_logger().warn(plan.get("message", "유효하지 않은 주문입니다."))
            return

        for order in plan["orders"]:
            queued_order = {
                "order_id": self.order_id,
                "table": order["table"],
                "item": order["item"],
                "count": order.get("count", 1)
            }

            self.order_id += 1

            out = String()
            out.data = json.dumps(queued_order, ensure_ascii=False)

            self.order_pub.publish(out)
            self.get_logger().info(f"/order_queue 발행: {out.data}")

    def validate_plan(self, plan):
        if not isinstance(plan, dict):
            return False

        if plan.get("valid") is not True:
            return False

        if "orders" not in plan:
            return False

        if not isinstance(plan["orders"], list):
            return False

        if len(plan["orders"]) == 0:
            return False

        for order in plan["orders"]:
            if not isinstance(order, dict):
                return False

            table = order.get("table")
            item = order.get("item")
            count = order.get("count", 1)

            if table not in self.allowed_tables:
                return False

            if item not in self.allowed_items:
                return False

            if not isinstance(count, int):
                return False

            if count <= 0:
                return False

        return True


def main(args=None):
    rclpy.init(args=args)

    node = OrderQueueNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()