#!/usr/bin/env python3
"""주문 태스크를 Action으로 전달."""

import json

import rclpy
from llm_serving_msgs.action import ServeTask
from rclpy.action import ActionClient
from rclpy.node import Node
from std_msgs.msg import String


class TaskExecutorNode(Node):
    def __init__(self):
        super().__init__('task_executor_node')
        self._action_client = ActionClient(self, ServeTask, 'serve_task')
        self._busy = False

        self.task_sub = self.create_subscription(
            String, 'llm_task', self._on_task, 10)
        self.get_logger().info('Task executor node ready.')

    def _on_task(self, msg: String):
        if self._busy:
            self.get_logger().warn('Busy — ignoring new task.')
            return

        try:
            task = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().error('Invalid task JSON.')
            return

        if task.get('action') != 'order':
            self.get_logger().warn(
                f'Unsupported action: {task.get("action")}')
            return

        self._busy = True
        self._execute_order(task)

    def _execute_order(self, task: dict):
        if not self._action_client.wait_for_server(timeout_sec=5.0):
            self.get_logger().error('ServeTask action server not available.')
            self._busy = False
            return

        goal = ServeTask.Goal()
        goal.destination = task.get('destination', 'kitchen')
        goal.items = task.get('items', [])
        goal.table_number = int(task.get('table', 0))

        self.get_logger().info(
            f'Sending order to kitchen: table={goal.table_number}, '
            f'items={goal.items}')

        send_future = self._action_client.send_goal_async(
            goal, feedback_callback=self._feedback_cb)
        send_future.add_done_callback(self._goal_response_cb)

    def _feedback_cb(self, feedback_msg):
        fb = feedback_msg.feedback
        self.get_logger().info(
            f'Progress: {fb.progress:.0%} — {fb.current_step}')

    def _goal_response_cb(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().error('Goal rejected.')
            self._busy = False
            return

        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self._result_cb)

    def _result_cb(self, future):
        result = future.result().result
        if result.success:
            self.get_logger().info(f'Task completed: {result.message}')
        else:
            self.get_logger().error(f'Task failed: {result.message}')
        self._busy = False


def main(args=None):
    rclpy.init(args=args)
    node = TaskExecutorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
