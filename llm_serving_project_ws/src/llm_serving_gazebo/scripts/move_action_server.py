#!/usr/bin/env python3
"""Task Executor 명령을 받아 Gazebo 로봇 이동 (cmd_vel 등)."""

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
            f'Goal: {goal_request.destination}, items={goal_request.items}')
        return GoalResponse.ACCEPT

    def _cancel_callback(self, goal_handle):
        return CancelResponse.ACCEPT

    async def _execute_callback(self, goal_handle):
        destination = goal_handle.request.destination
        items = goal_handle.request.items

        feedback = ServeTask.Feedback()
        result = ServeTask.Result()

        steps = [
            ('navigating_to_kitchen', 0.3),
            ('loading_items', 0.5),
            (f'navigating_to_{destination}', 0.8),
            ('delivering', 1.0),
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

            # TODO: restaurant_map.yaml 좌표 기반 실제 내비게이션
            twist = Twist()
            twist.linear.x = 0.1
            self.cmd_pub.publish(twist)

            await self._sleep(1.0)

        stop = Twist()
        self.cmd_pub.publish(stop)

        result.success = True
        result.message = f'Delivered {items} to {destination}'
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
