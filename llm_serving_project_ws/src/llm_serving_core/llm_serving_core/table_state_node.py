#!/usr/bin/env python3
"""테이블별 손님 수 공유 상태 — 배열 소유, 토픽 발행, 서비스 제공."""

import json
import os

import rclpy
import yaml
from ament_index_python.packages import get_package_share_directory
from llm_serving_msgs.msg import TableStatus
from llm_serving_msgs.srv import LeaveTable, SeatGuests
from rclpy.node import Node
from std_msgs.msg import String


class TableStateNode(Node):
    def __init__(self):
        super().__init__('table_state_node')

        share_dir = get_package_share_directory('llm_serving_core')
        map_path = os.path.join(share_dir, 'config', 'restaurant_map.yaml')
        with open(map_path, 'r', encoding='utf-8') as f:
            restaurant_map = yaml.safe_load(f)

        tables = restaurant_map.get('tables', [])
        self._table_names = [t['name'] for t in tables]
        self._max_seats = [int(t.get('max_seats', 4)) for t in tables]
        self._guest_counts = [0] * len(tables)

        self.status_pub = self.create_publisher(TableStatus, 'table_status', 10)
        self.create_subscription(String, 'guest_command', self._on_guest_command, 10)
        self.create_service(SeatGuests, 'seat_guests', self._handle_seat)
        self.create_service(LeaveTable, 'leave_table', self._handle_leave)
        self.create_timer(2.0, self._publish_status)

        self._publish_status()
        self.get_logger().info(
            f'Table state node ready ({len(self._table_names)} tables).')

    def _table_label(self, index: int) -> str:
        return self._table_names[index]

    def _format_status(self) -> str:
        parts = []
        for i, count in enumerate(self._guest_counts):
            label = self._table_label(i)
            if count == 0:
                parts.append(f'{label}: empty')
            else:
                parts.append(f'{label}: {count} guests')
        return ', '.join(parts)

    def _publish_status(self):
        msg = TableStatus()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'restaurant'
        msg.guest_counts = list(self._guest_counts)
        self.status_pub.publish(msg)

    def _find_empty_table(self, party_size: int) -> int | None:
        for i, count in enumerate(self._guest_counts):
            if count == 0 and party_size <= self._max_seats[i]:
                return i
        return None

    def _seat_guests(self, party_size: int, table_number: int = 0) -> tuple[bool, int, str]:
        if party_size == 0:
            return False, 0, 'party_size must be greater than 0'

        if table_number > 0:
            index = table_number - 1
            if index < 0 or index >= len(self._guest_counts):
                return False, 0, f'invalid table number: {table_number}'
            if self._guest_counts[index] != 0:
                return False, 0, f'{self._table_label(index)} is not empty'
            if party_size > self._max_seats[index]:
                return False, 0, (
                    f'{self._table_label(index)} max seats is '
                    f'{self._max_seats[index]}')
            self._guest_counts[index] = party_size
            self._publish_status()
            return True, table_number, (
                f'Seated {party_size} guests at {self._table_label(index)}')

        index = self._find_empty_table(party_size)
        if index is None:
            return False, 0, 'no available empty table'

        self._guest_counts[index] = party_size
        assigned = index + 1
        self._publish_status()
        return True, assigned, (
            f'Seated {party_size} guests at {self._table_label(index)}')

    def _leave_table(self, table_number: int) -> tuple[bool, str]:
        if table_number == 0:
            return False, 'table_number must be greater than 0'

        index = table_number - 1
        if index < 0 or index >= len(self._guest_counts):
            return False, f'invalid table number: {table_number}'
        if self._guest_counts[index] == 0:
            return False, f'{self._table_label(index)} is already empty'

        self._guest_counts[index] = 0
        self._publish_status()
        return True, f'{self._table_label(index)} cleared'

    def _handle_seat(self, request, response):
        success, assigned, message = self._seat_guests(
            request.party_size, request.table_number)
        response.success = success
        response.assigned_table = assigned
        response.message = message
        level = self.get_logger().info if success else self.get_logger().warn
        level(message)
        return response

    def _handle_leave(self, request, response):
        success, message = self._leave_table(request.table_number)
        response.success = success
        response.message = message
        level = self.get_logger().info if success else self.get_logger().warn
        level(message)
        return response

    def _on_guest_command(self, msg: String):
        try:
            cmd = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().warn(f'Invalid guest_command JSON: {msg.data}')
            return

        event = cmd.get('event')
        if event == 'arrive':
            table = int(cmd.get('table', 0))
            count = int(cmd.get('count', 0))
            success, assigned, message = self._seat_guests(count, table)
            level = self.get_logger().info if success else self.get_logger().warn
            level(message)
        elif event == 'leave':
            table = int(cmd.get('table', 0))
            success, message = self._leave_table(table)
            level = self.get_logger().info if success else self.get_logger().warn
            level(message)
        elif event == 'status':
            self.get_logger().info(f'Table status: {self._format_status()}')
        else:
            self.get_logger().warn(f'Unknown guest event: {event}')


def main(args=None):
    rclpy.init(args=args)
    node = TableStateNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
