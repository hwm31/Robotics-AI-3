#!/usr/bin/env python3
"""주문을 받아 주방으로 이동 후 주문 내용을 알림."""

import rclpy
from geometry_msgs.msg import Twist
from llm_serving_msgs.action import ServeTask
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.node import Node


class MoveActionServer(Node):
    def __init__(self):
        super().__init__('move_action_server')
        self.declare_parameter('cmd_vel_topic', 'cmd_vel_raw')

        cmd_topic = self.get_parameter('cmd_vel_topic').value
        self.cmd_pub = self.create_publisher(Twist, cmd_topic, 10)

        self._action_server = ActionServer(
            self,
            ServeTask,
            'serve_task',
            self._execute_callback,
            callback_group=ReentrantCallbackGroup(),
            goal_callback=self._goal_callback,
            cancel_callback=self._cancel_callback,
        )
        self.get_logger().info('ServeTask action server ready.')

    def _goal_callback(self, goal_request):
        self.get_logger().info(
            f'Order goal: table={goal_request.table_number}, '
            f'items={goal_request.items}')
        if goal_request.table_number <= 0:
            self.get_logger().warn('Rejected: table_number is required.')
            return GoalResponse.REJECT
        if not goal_request.items:
            self.get_logger().warn('Rejected: no items in order.')
            return GoalResponse.REJECT
        return GoalResponse.ACCEPT

    def _cancel_callback(self, goal_handle):
        return CancelResponse.ACCEPT

    async def _execute_callback(self, goal_handle):
        table_number = goal_handle.request.table_number
        items = goal_handle.request.items

        feedback = ServeTask.Feedback()
        result = ServeTask.Result()

        steps = [
            ('navigating_to_kitchen', 0.5),
            ('announcing_order', 1.0),
        ]

        for step_name, progress in steps:
            if goal_handle.is_cancel_requested:
                goal_handle.canceled()
                result.success = False
                result.message = 'Canceled'
                return result

            feedback.current_step = step_name
            feedback.progress = progress
            goal_handle.publish_feedback(feedback)
            self.get_logger().info(f'Step: {step_name}')

            if step_name == 'navigating_to_kitchen':
                # TODO: restaurant_map.yaml kitchen 좌표 기반 실제 내비게이션
                twist = Twist()
                twist.linear.x = 0.1
                self.cmd_pub.publish(twist)
                await self._sleep(1.0)
                stop = Twist()
                self.cmd_pub.publish(stop)
            elif step_name == 'announcing_order':
                item_labels = ', '.join(items)
                announcement = (
                    f'Table {table_number} ordered: {item_labels}'
                )
                print(f'\n=== Kitchen ===\nRobot: {announcement}\n')
                self.get_logger().info(announcement)

        result.success = True
        result.message = (
            f'Relayed order to kitchen — table {table_number}: {items}'
        )
        goal_handle.succeed()
        return result

    async def _sleep(self, seconds: float):
        import asyncio
        await asyncio.sleep(seconds)


def main(args=None):
    rclpy.init(args=args)
    node = MoveActionServer()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
