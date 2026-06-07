#!/usr/bin/env python3
"""서빙 로봇 관제탑: 좌석 안내, 주문 큐, 로봇 배차."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import json
import os
import threading

import rclpy
import yaml
from ament_index_python.packages import get_package_share_directory
from llm_serving_msgs.action import ServeTask
from llm_serving_msgs.srv import SeatGuests
from rclpy.action import ActionClient
from rclpy.node import Node
from std_msgs.msg import String


@dataclass
class QueuedOrder:
    order_id: int
    table: int
    items: list[str]
    item_counts: list[dict]
    destination: str = 'kitchen'
    source: str = 'llm_task'


class FleetManagerNode(Node):
    def __init__(self):
        super().__init__('fleet_manager_node')

        self.declare_parameter('robot_action_names', ['serve_task'])
        self.declare_parameter('dispatch_period', 0.5)

        self.robot_clients: dict[str, ActionClient] = {}
        self.robot_action_names: dict[str, str] = {}
        self.robot_states: dict[str, str] = {}
        self._create_robot_clients()

        self.seat_client = self.create_client(SeatGuests, 'seat_guests')
        self.greeting_goal_pub = self.create_publisher(
            String,
            'greeting_move_goal',
            10,
        )

        self.llm_sub = self.create_subscription(String, 'llm_task', self._on_llm_task, 10)
        self.kitchen_sub = self.create_subscription(String, 'food_ready', self._on_food_ready, 10)
        self.table_assignment_sub = self.create_subscription(
            String,
            'table_assignment',
            self._on_table_assignment,
            10,
        )

        self.order_queue: deque[QueuedOrder] = deque()
        self.queue_lock = threading.Lock()
        self.next_order_id = 1
        self._last_unavailable_log: dict[str, float] = {}
        self.table_coordinates = self._load_table_coordinates()

        self.create_timer(
            float(self.get_parameter('dispatch_period').value),
            self._dispatch_queued_orders,
        )

        self.get_logger().info(
            'Fleet manager ready. Robots: '
            + ', '.join(
                f'{robot_id}({action})'
                for robot_id, action in self.robot_action_names.items()
            )
        )

    def _create_robot_clients(self):
        action_names = self._configured_robot_action_names()
        for index, action_name in enumerate(action_names, start=1):
            robot_id = f'robot{index}'
            self.robot_clients[robot_id] = ActionClient(
                self,
                ServeTask,
                action_name,
            )
            self.robot_action_names[robot_id] = action_name
            self.robot_states[robot_id] = 'IDLE'

    def _configured_robot_action_names(self) -> list[str]:
        value = self.get_parameter('robot_action_names').value
        if isinstance(value, str):
            names = [part.strip() for part in value.split(',')]
        else:
            names = [str(part).strip() for part in value]

        names = [name for name in names if name]
        return names or ['serve_task']

    def _load_table_coordinates(self) -> dict[int, dict[str, float]]:
        share_dir = get_package_share_directory('llm_serving_core')
        map_path = os.path.join(share_dir, 'config', 'restaurant_map.yaml')

        with open(map_path, 'r', encoding='utf-8') as f:
            restaurant_map = yaml.safe_load(f) or {}

        coordinates: dict[int, dict[str, float]] = {}
        for index, table in enumerate(restaurant_map.get('tables', []), start=1):
            table_number = self._coerce_table_number(table.get('name')) or index
            coordinates[table_number] = {
                'x': float(table['x']),
                'y': float(table['y']),
                'yaw': float(table.get('yaw', 0.0)),
            }

        return coordinates

    def _get_idle_robot(self):
        """현재 쉬고 있는(IDLE) 로봇을 찾아 반환합니다."""
        for r_id, state in self.robot_states.items():
            if state == 'IDLE':
                return r_id
        return None

    def _on_llm_task(self, msg: String):
        """LLM이 파싱한 JSON 명령 처리"""
        try:
            task = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().error('Invalid JSON received.')
            return

        intent = task.get('intent')

        if intent == 'greeting':
            party_size = task.get('people', 1)
            self._request_seat_assignment(party_size)

        elif intent == 'order':
            enqueued = self._enqueue_orders_from_task(task)
            if enqueued:
                self._dispatch_queued_orders()

        else:
            self.get_logger().warn(f"Unknown intent: {intent}")

    def _request_seat_assignment(self, party_size):
        """table_state_node에 빈자리 할당을 요청하는 서비스 콜"""
        if not self.seat_client.wait_for_service(timeout_sec=3.0):
            self.get_logger().error('/seat_guests 서비스가 응답하지 않습니다.')
            return
            
        req = SeatGuests.Request()
        req.party_size = int(party_size)
        req.table_number = 0  # 0이면 시스템이 알아서 빈 테이블 배정
        
        future = self.seat_client.call_async(req)
        future.add_done_callback(lambda f: self._seat_assigned_cb(f, party_size))

    def _seat_assigned_cb(self, future, party_size):
        """빈자리 배정 완료 후 안내 로봇 출발"""
        try:
            response = future.result()
            if response.success:
                target_table = response.assigned_table
                self.get_logger().info(
                    f"[안내] {party_size}명 -> Table {target_table} 배정 성공.")
                self._publish_greeting_move_goal(target_table)
            else:
                self.get_logger().warn("만석입니다! 빈 테이블이 없습니다.")
        except Exception as e:
            self.get_logger().error(f"좌석 배정 서비스 실패: {e}")

    def _on_table_assignment(self, msg: String):
        try:
            data = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().error(f"Invalid table_assignment JSON: {msg.data}")
            return

        if data.get('success') is False:
            return

        table = self._coerce_table_number(data.get('table_id', data.get('table')))
        if table is None:
            self.get_logger().warn(f"table_assignment에 table 정보가 없습니다: {data}")
            return

        self._publish_greeting_move_goal(table)

    def _publish_greeting_move_goal(self, table: int):
        coordinates = self.table_coordinates.get(int(table))
        if coordinates is None:
            self.get_logger().warn(f"Table {table} 좌표가 없어 안내 이동을 생략합니다.")
            return

        msg = String()
        msg.data = json.dumps(
            {
                'task': 'guide_customer',
                'table_id': int(table),
                'x': coordinates['x'],
                'y': coordinates['y'],
                'yaw': coordinates['yaw'],
            },
            ensure_ascii=False,
        )
        self.greeting_goal_pub.publish(msg)
        self.get_logger().info(f"Published greeting move goal: {msg.data}")

    def _on_food_ready(self, msg: String):
        """주방 신호 처리 (배달) - 예외 처리 및 방어 로직 적용"""
        
        # 1. JSON 포맷 오류 방어 로직
        try:
            data = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().error("[예외 처리] 주방 신호 포맷 오류: 유효한 JSON이 아닙니다. 로봇 대기 유지.")
            return  # 시스템을 다운시키지 않고 해당 명령만 무시 (에러 필터링)

        # 2. 필수 데이터 누락 방어 로직
        target_table = data.get('table')
        if target_table is None:
            self.get_logger().error("[예외 처리] 주방 신호 오류: 목적지(table) 정보가 누락되었습니다. 배차 취소.")
            return

        items = data.get('items') or ['food']
        self._enqueue_order(
            table=target_table,
            items=self._normalize_item_list(items),
            item_counts=self._item_counts_from_items(items),
            destination='table',
            source='food_ready',
        )
        self._dispatch_queued_orders()

    def _enqueue_orders_from_task(self, task: dict) -> bool:
        raw_orders = task.get('orders')
        if not raw_orders:
            raw_orders = [{
                'table': task.get('table'),
                'items': task.get('item_counts', task.get('items')),
                'expanded_items': task.get('items'),
            }]
        elif isinstance(raw_orders, dict):
            raw_orders = [raw_orders]

        if not isinstance(raw_orders, list):
            self.get_logger().warn(f"orders 형식이 잘못되었습니다: {raw_orders}")
            return False

        enqueued = False
        for raw_order in raw_orders:
            if not isinstance(raw_order, dict):
                self.get_logger().warn(f"잘못된 주문 항목: {raw_order}")
                continue

            table = self._coerce_table_number(raw_order.get('table', task.get('table')))
            items = raw_order.get('expanded_items')
            if not items:
                items = self._normalize_item_list(
                    raw_order.get('items', raw_order.get('item_counts', [])))

            item_counts = raw_order.get('items')
            if not self._looks_like_item_counts(item_counts):
                item_counts = raw_order.get('item_counts')
            if not self._looks_like_item_counts(item_counts):
                item_counts = self._item_counts_from_items(items)

            if self._enqueue_order(
                table=table,
                items=self._normalize_item_list(items),
                item_counts=item_counts,
                destination=task.get('destination', 'kitchen'),
                source='llm_task',
            ):
                enqueued = True

        return enqueued

    def _enqueue_order(
        self,
        table,
        items: list[str],
        item_counts: list[dict],
        destination: str,
        source: str,
    ) -> bool:
        table_number = self._coerce_table_number(table)
        if table_number is None or table_number <= 0:
            self.get_logger().warn(f"주문 테이블이 잘못되었습니다: {table}")
            return False

        if not items:
            self.get_logger().warn(f"주문 메뉴가 비어 있습니다: table={table_number}")
            return False

        with self.queue_lock:
            order = QueuedOrder(
                order_id=self.next_order_id,
                table=table_number,
                items=items,
                item_counts=item_counts,
                destination=destination,
                source=source,
            )
            self.next_order_id += 1
            self.order_queue.append(order)
            queue_size = len(self.order_queue)

        self.get_logger().info(
            f"[큐] order_id={order.order_id}, table={order.table}, "
            f"items={order.item_counts}, 대기={queue_size}"
        )
        return True

    def _dispatch_queued_orders(self):
        while True:
            idle_robot = self._get_idle_robot()
            if idle_robot is None:
                return

            with self.queue_lock:
                if not self.order_queue:
                    return
                order = self.order_queue[0]

            if not self._send_goal(idle_robot, order):
                return

            with self.queue_lock:
                if self.order_queue and self.order_queue[0].order_id == order.order_id:
                    self.order_queue.popleft()

    def _send_goal(self, robot_id: str, order: QueuedOrder) -> bool:
        """선택된 로봇에게 액션 목표(Goal) 전송"""
        client = self.robot_clients[robot_id]
        action_name = self.robot_action_names[robot_id]

        if not client.wait_for_server(timeout_sec=0.2):
            self._log_action_unavailable(robot_id, action_name)
            return False

        goal = ServeTask.Goal()
        goal.destination = order.destination
        goal.table_number = int(order.table)
        goal.items = list(order.items)

        self.robot_states[robot_id] = 'BUSY'

        self.get_logger().info(
            f"[배차] order_id={order.order_id}, {robot_id} -> "
            f"table={goal.table_number}, items={goal.items}"
        )

        send_future = client.send_goal_async(goal)
        send_future.add_done_callback(
            lambda future, r_id=robot_id, sent=order:
            self._goal_response_cb(future, r_id, sent)
        )
        return True

    def _goal_response_cb(self, future, robot_id: str, order: QueuedOrder):
        try:
            goal_handle = future.result()
        except Exception as exc:
            self.get_logger().error(
                f'{robot_id} order_id={order.order_id} goal 전송 실패: {exc}')
            self.robot_states[robot_id] = 'IDLE'
            self._dispatch_queued_orders()
            return

        if not goal_handle.accepted:
            self.get_logger().error(
                f'{robot_id}가 order_id={order.order_id} 목표를 거부했습니다.')
            self.robot_states[robot_id] = 'IDLE'
            self._dispatch_queued_orders()
            return

        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(
            lambda future, r_id=robot_id, sent=order:
            self._result_cb(future, r_id, sent)
        )

    def _result_cb(self, future, robot_id: str, order: QueuedOrder):
        """로봇 임무 완료 시 호출"""
        try:
            result = future.result().result
        except Exception as exc:
            self.get_logger().error(
                f'[{robot_id} 임무 결과 수신 실패] order_id={order.order_id}: {exc}')
            self.robot_states[robot_id] = 'IDLE'
            self._dispatch_queued_orders()
            return

        level = self.get_logger().info if result.success else self.get_logger().error
        level(f'[{robot_id} 임무 완료] order_id={order.order_id}: {result.message}')
        self.robot_states[robot_id] = 'IDLE'
        self._dispatch_queued_orders()

    def _log_action_unavailable(self, robot_id: str, action_name: str):
        now = self.get_clock().now().nanoseconds / 1_000_000_000
        last = self._last_unavailable_log.get(robot_id, 0.0)
        if now - last < 5.0:
            return
        self._last_unavailable_log[robot_id] = now
        self.get_logger().error(f'{robot_id} 액션 서버({action_name})가 열려있지 않습니다.')

    def _coerce_table_number(self, value) -> int | None:
        if value is None:
            return None
        if isinstance(value, int):
            return value

        text = str(value).strip()
        if text.isdigit():
            return int(text)

        import re
        match = re.search(r'(\d+)', text)
        if match:
            return int(match.group(1))
        return None

    def _looks_like_item_counts(self, value) -> bool:
        return (
            isinstance(value, list)
            and all(isinstance(entry, dict) and 'item' in entry for entry in value)
        )

    def _normalize_item_list(self, raw_items) -> list[str]:
        if raw_items is None:
            return []
        if isinstance(raw_items, str):
            return [raw_items]
        if isinstance(raw_items, dict):
            raw_items = [raw_items]
        if not isinstance(raw_items, list):
            return []

        items: list[str] = []
        for entry in raw_items:
            if isinstance(entry, str):
                item = entry.strip()
                if item:
                    items.append(item)
            elif isinstance(entry, dict):
                item = str(entry.get('item') or '').strip()
                if not item:
                    continue
                try:
                    count = int(entry.get('count', 1))
                except (TypeError, ValueError):
                    count = 1
                items.extend([item] * max(1, count))
        return items

    def _item_counts_from_items(self, raw_items) -> list[dict]:
        items = self._normalize_item_list(raw_items)
        counts: dict[str, int] = {}
        order: list[str] = []
        for item in items:
            if item not in counts:
                order.append(item)
                counts[item] = 0
            counts[item] += 1
        return [{'item': item, 'count': counts[item]} for item in order]


def main(args=None):
    rclpy.init(args=args)
    node = FleetManagerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
