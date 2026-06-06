#!/usr/bin/env python3

"""
서빙 작업 실행 노드 — 주문 큐 수신, 주방 이동, 음식 픽업, 테이블 서빙 수행.

기능:
- /order_queue 토픽 수신
- /table_location 토픽 수신
- 주문을 내부 큐(deque)에 순서대로 저장
- 주방 위치로 이동
- 음식 픽업 상태 처리
- 해당 테이블로 이동 후 서빙 완료 처리
- 대기 위치로 복귀
- /robot_status_update 토픽 발행
"""

import json
import time
import threading
from collections import deque

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from geometry_msgs.msg import PoseStamped
from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult


class ServingTaskNode(Node):
    def __init__(self):
        super().__init__('serving_task_node')

        self.nav = BasicNavigator()

        self.order_sub = self.create_subscription(
            String,
            '/order_queue',
            self.order_callback,
            10
        )

        self.status_pub = self.create_publisher(
            String,
            '/robot_status_update',
            10
        )

        #일단 임의로 웨이팅 존하고 주방 위치 잡아놨는데 나중에 맵에 맞게 고치면 됩니다.
        self.locations = {
            "waiting_zone": (0.0, 0.0),
            "kitchen": (1.0, 0.0),
        }
         
        #토픽 이름에 따라 변경
        self.table_location_sub = self.create_subscription(
            String,
            '/table_location',
            self.table_location_callback,
            10
        )

        self.order_queue = deque()
        self.queue_lock = threading.Lock()

        self.current_location = "waiting_zone"
        self.carrying = "None"

        self.worker_thread = threading.Thread(
            target=self.serving_worker,
            daemon=True
        )
        self.worker_thread.start()

        self.get_logger().info("=== serving_task_node 시작 ===")
        self.get_logger().info("주문 큐 대기 중...")

    def order_callback(self, msg):
        try:
            order = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().error("주문 JSON 파싱 실패")
            return

        if not self.validate_order(order):
            self.get_logger().warn(f"잘못된 주문 형식: {order}")
            return

        with self.queue_lock:
            self.order_queue.append(order)
            queue_size = len(self.order_queue)

        self.get_logger().info(
            f"주문 큐 추가: "
            f"order_id={order['order_id']}, "
            f"table={order['table']}, "
            f"item={order['item']}, "
            f"count={order['count']}, "
            f"대기={queue_size}"
        )
    def table_location_callback(self, msg):
        try:
            data = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().error("/table_location JSON 파싱 실패")
            return

        table = data.get("table")
        x = data.get("x")
        y = data.get("y")

        if table is None or x is None or y is None:
            self.get_logger().warn(f"/table_location 데이터 부족: {data}")
            return

        if table not in [f"table_{i}" for i in range(1, 13)]:
            self.get_logger().warn(f"허용되지 않은 테이블 이름: {table}")
            return

        try:
            x = float(x)
            y = float(y)
        except ValueError:
            self.get_logger().warn(f"좌표값이 숫자가 아닙니다: x={x}, y={y}")
            return

        self.locations[table] = (x, y)

        self.get_logger().info(
            f"테이블 좌표 저장: {table} → x={x}, y={y}"
        )

    def validate_order(self, order):
        for key in ["order_id", "table", "item", "count"]:
            if key not in order:
                return False

        if order["table"] not in self.locations:
            return False

        if not isinstance(order["count"], int):
            return False

        if order["count"] <= 0:
            return False

        return True

    def serving_worker(self):
        while rclpy.ok():
            order = None

            with self.queue_lock:
                if len(self.order_queue) > 0:
                    order = self.order_queue.popleft()

            if order is None:
                time.sleep(0.2)
                continue

            self.process_order(order)

    def process_order(self, order):
        order_id = order["order_id"]
        table = order["table"]
        item = order["item"]
        count = order["count"]

        self.get_logger().info(
            f"===== 주문 처리 시작 =====\n"
            f"주문번호: {order_id}\n"
            f"테이블: {table}\n"
            f"메뉴: {item}\n"
            f"개수: {count}"
        )

        self.publish_status("moving_to_kitchen", "kitchen", self.carrying)

        if self.move_to_location("kitchen") != TaskResult.SUCCEEDED:
            self.publish_status("error", self.current_location, self.carrying)
            return

        self.current_location = "kitchen"

        self.pickup_item(item, count)

        self.publish_status("moving_to_table", table, self.carrying)

        if self.move_to_location(table) != TaskResult.SUCCEEDED:
            self.publish_status("error", self.current_location, self.carrying)
            return

        self.current_location = table

        self.dropoff_item(item, table)

        self.publish_status("returning", "waiting_zone", self.carrying)

        if self.move_to_location("waiting_zone") == TaskResult.SUCCEEDED:
            self.current_location = "waiting_zone"
            self.publish_status("idle", self.current_location, self.carrying)

        self.get_logger().info(f"===== 주문 처리 완료: {order_id} =====")

    def move_to_location(self, location_name):
        if location_name not in self.locations:
            self.get_logger().error(f"알 수 없는 위치: {location_name}")
            return TaskResult.FAILED

        x, y = self.locations[location_name]

        goal_pose = PoseStamped()
        goal_pose.header.frame_id = "map"
        goal_pose.header.stamp = self.nav.get_clock().now().to_msg()

        goal_pose.pose.position.x = x
        goal_pose.pose.position.y = y
        goal_pose.pose.orientation.w = 1.0

        self.get_logger().info(
            f"이동 시작: {location_name} → x={x}, y={y}"
        )

        self.nav.goToPose(goal_pose)

        while not self.nav.isTaskComplete():
            time.sleep(0.1)

        result = self.nav.getResult()

        if result == TaskResult.SUCCEEDED:
            self.get_logger().info(f"도착 완료: {location_name}")
        else:
            self.get_logger().warn(f"이동 실패 또는 취소: {location_name}")

        return result

    def pickup_item(self, item, count):
        self.carrying = item
        self.get_logger().info(f"🍽 음식 픽업 완료: {item} {count}개")
        self.publish_status("pickup", self.current_location, self.carrying)
        time.sleep(1.0)

    def dropoff_item(self, item, table):
        self.get_logger().info(f"✅ 서빙 완료: {table}에 {item} 전달")
        self.carrying = "None"
        self.publish_status("serving_complete", table, self.carrying)
        time.sleep(1.0)

    def publish_status(self, state, location, carrying):
        msg = String()
        msg.data = json.dumps(
            {
                "state": state,
                "location": location,
                "carrying": carrying
            },
            ensure_ascii=False
        )

        self.status_pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)

    node = ServingTaskNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()