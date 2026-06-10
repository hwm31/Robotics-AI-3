#!/usr/bin/env python3
"""ServeTask goals backed by Nav2 navigation."""

from __future__ import annotations

import json
import math
import os
import threading
import time
from dataclasses import dataclass

import rclpy
import yaml
from action_msgs.msg import GoalStatus
from ament_index_python.packages import get_package_share_directory
from geometry_msgs.msg import PoseStamped, PoseWithCovarianceStamped
from llm_serving_msgs.action import ServeTask
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient, ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from std_msgs.msg import String


@dataclass(frozen=True)
class MapPose:
    x: float
    y: float
    yaw: float = 0.0


class MoveActionServer(Node):
    def __init__(self):
        super().__init__('move_action_server')
        self.declare_parameter('nav_action_name', 'navigate_to_pose')
        self.declare_parameter('nav_server_timeout', 20.0)
        self.declare_parameter('goal_timeout', 120.0)
        self.declare_parameter('return_home_after_serving', True)
        self.declare_parameter('publish_initial_pose', True)

        self._nav_server_timeout = float(
            self.get_parameter('nav_server_timeout').value)
        self._goal_timeout = float(self.get_parameter('goal_timeout').value)
        self._return_home = bool(
            self.get_parameter('return_home_after_serving').value)
        self._publish_initial_pose_enabled = bool(
            self.get_parameter('publish_initial_pose').value)

        callback_group = ReentrantCallbackGroup()
        nav_action_name = self.get_parameter('nav_action_name').value
        self._nav_action_name = str(nav_action_name)
        self._nav_client = ActionClient(
            self,
            NavigateToPose,
            nav_action_name,
            callback_group=callback_group,
        )
        self._action_server = ActionServer(
            self,
            ServeTask,
            'serve_task',
            self._execute_callback,
            callback_group=callback_group,
            goal_callback=self._goal_callback,
            cancel_callback=self._cancel_callback,
        )

        self._initial_pose_pub = self.create_publisher(
            PoseWithCovarianceStamped,
            '/initialpose',
            10,
        )
        self._greeting_sub = self.create_subscription(
            String,
            'greeting_move_goal',
            self._on_greeting_move_goal,
            10,
            callback_group=callback_group,
        )

        self._poses = self._load_restaurant_poses()
        self._navigation_lock = threading.Lock()
        self._initial_pose_sent = True

        if self._publish_initial_pose_enabled and 'home' in self._poses:
            self._initial_pose_sent = False
            self.create_timer(2.0, self._publish_home_initial_pose_once)

        self.get_logger().info('ServeTask Nav2 action server ready.')

    def _load_restaurant_poses(self) -> dict[str, MapPose]:
        share_dir = get_package_share_directory('llm_serving_core')
        map_path = os.path.join(share_dir, 'config', 'restaurant_map.yaml')

        with open(map_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}

        poses: dict[str, MapPose] = {}
        for key in ('kitchen', 'home'):
            if key in data:
                poses[key] = self._pose_from_dict(data[key])

        for index, table in enumerate(data.get('tables', []), start=1):
            poses[f'table_{index}'] = self._pose_from_dict(table)

        self.get_logger().info(
            f'Loaded navigation targets: {", ".join(sorted(poses))}')
        return poses

    def _pose_from_dict(self, data: dict) -> MapPose:
        return MapPose(
            x=float(data['x']),
            y=float(data['y']),
            yaw=float(data.get('yaw', 0.0)),
        )

    def _goal_callback(self, goal_request):
        destination = (goal_request.destination or 'table').strip().lower()
        items = list(goal_request.items)
        self.get_logger().info(
            f'ServeTask goal: destination={destination}, '
            f'table={goal_request.table_number}, items={items}')
        if destination not in ('table', 'kitchen'):
            self.get_logger().warn(
                f'Rejected: unsupported destination: {destination}.')
            return GoalResponse.REJECT
        if goal_request.table_number <= 0:
            self.get_logger().warn('Rejected: table_number is required.')
            return GoalResponse.REJECT
        if f'table_{goal_request.table_number}' not in self._poses:
            self.get_logger().warn(
                f'Rejected: no navigation target for table '
                f'{goal_request.table_number}.')
            return GoalResponse.REJECT
        if destination == 'kitchen' and not items:
            self.get_logger().warn('Rejected: kitchen task requires items.')
            return GoalResponse.REJECT
        return GoalResponse.ACCEPT

    def _cancel_callback(self, goal_handle):
        self.get_logger().warn('ServeTask cancel requested.')
        return CancelResponse.ACCEPT

    def _execute_callback(self, goal_handle):
        if not self._navigation_lock.acquire(blocking=False):
            result = ServeTask.Result()
            result.success = False
            result.message = 'Robot is already navigating'
            goal_handle.abort()
            return result

        try:
            destination = (goal_handle.request.destination or 'table').strip().lower()
            items = list(goal_handle.request.items)
            if destination == 'table' and not items:
                result = self._execute_guiding_sequence(goal_handle)
            else:
                result = self._execute_serving_sequence(goal_handle)
        finally:
            self._navigation_lock.release()

        return result

    def _execute_guiding_sequence(self, goal_handle):
        table_number = int(goal_handle.request.table_number)
        table_key = f'table_{table_number}'

        result = ServeTask.Result()
        steps: list[tuple[str, str, float, float]] = [
            ('guiding_to_table', table_key, 0.0, 0.85),
        ]
        if self._return_home and 'home' in self._poses:
            steps.append(('returning_home', 'home', 0.88, 1.0))

        for step_name, target_key, start_progress, end_progress in steps:
            if goal_handle.is_cancel_requested:
                goal_handle.canceled()
                result.success = False
                result.message = 'Canceled'
                return result

            ok, message = self._navigate_to_target(
                target_key,
                step_name,
                goal_handle=goal_handle,
                start_progress=start_progress,
                end_progress=end_progress,
            )
            if not ok:
                if goal_handle.is_cancel_requested:
                    goal_handle.canceled()
                else:
                    goal_handle.abort()
                result.success = False
                result.message = message
                return result

        result.success = True
        result.message = f'Guided guests to table {table_number}'
        self._publish_feedback(goal_handle, 'completed', 1.0)
        goal_handle.succeed()
        return result

    def _execute_serving_sequence(self, goal_handle):
        table_number = int(goal_handle.request.table_number)
        items = list(goal_handle.request.items)
        table_key = f'table_{table_number}'

        result = ServeTask.Result()
        steps: list[tuple[str, str | None, float, float]] = [
            ('navigating_to_kitchen', 'kitchen', 0.05, 0.35),
            ('announcing_order', None, 0.40, 0.45),
            ('navigating_to_table', table_key, 0.50, 0.80),
            ('delivering_order', None, 0.85, 0.90),
        ]
        if self._return_home and 'home' in self._poses:
            steps.append(('returning_home', 'home', 0.92, 1.0))

        for step_name, target_key, start_progress, end_progress in steps:
            if goal_handle.is_cancel_requested:
                goal_handle.canceled()
                result.success = False
                result.message = 'Canceled'
                return result

            if target_key is None:
                self._publish_feedback(goal_handle, step_name, end_progress)
                self._announce_step(step_name, table_number, items)
                continue

            ok, message = self._navigate_to_target(
                target_key,
                step_name,
                goal_handle=goal_handle,
                start_progress=start_progress,
                end_progress=end_progress,
            )
            if not ok:
                if goal_handle.is_cancel_requested:
                    goal_handle.canceled()
                else:
                    goal_handle.abort()
                result.success = False
                result.message = message
                return result

        result.success = True
        result.message = (
            f'Served table {table_number}: {", ".join(items)}'
        )
        self._publish_feedback(goal_handle, 'completed', 1.0)
        goal_handle.succeed()
        return result

    def _announce_step(
        self,
        step_name: str,
        table_number: int,
        items: list[str],
    ) -> None:
        if step_name == 'announcing_order':
            item_labels = ', '.join(items)
            announcement = f'Table {table_number} ordered: {item_labels}'
            print(f'\n=== Kitchen ===\nRobot: {announcement}\n')
            self.get_logger().info(announcement)
        elif step_name == 'delivering_order':
            self.get_logger().info(
                f'Delivered order to table {table_number}: {items}')
            print(f'\n=== Table {table_number} ===\nRobot: Here is your order.\n')

    def _on_greeting_move_goal(self, msg: String):
        try:
            data = json.loads(msg.data)
            table_id = int(data['table_id'])
            pose = MapPose(
                x=float(data['x']),
                y=float(data['y']),
                yaw=float(data.get('yaw', 0.0)),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self.get_logger().error(
                f'Invalid greeting_move_goal: {exc}; data={msg.data}')
            return

        def _run():
            if not self._navigation_lock.acquire(blocking=False):
                self.get_logger().warn(
                    f'Ignoring table {table_id} guide request: robot is busy.')
                return
            try:
                self.get_logger().info(
                    f'Guiding customer to table {table_id}.')
                self._navigate_to_pose(
                    pose,
                    f'guiding_to_table_{table_id}',
                    goal_handle=None,
                    start_progress=0.0,
                    end_progress=1.0,
                )
            finally:
                self._navigation_lock.release()

        threading.Thread(target=_run, daemon=True).start()

    def _navigate_to_target(
        self,
        target_key: str,
        step_name: str,
        goal_handle,
        start_progress: float,
        end_progress: float,
    ) -> tuple[bool, str]:
        pose = self._poses.get(target_key)
        if pose is None:
            return False, f'No navigation target configured: {target_key}'

        return self._navigate_to_pose(
            pose,
            step_name,
            goal_handle,
            start_progress,
            end_progress,
        )

    def _navigate_to_pose(
        self,
        pose: MapPose,
        step_name: str,
        goal_handle,
        start_progress: float,
        end_progress: float,
    ) -> tuple[bool, str]:
        if not self._nav_client.wait_for_server(
            timeout_sec=self._nav_server_timeout
        ):
            message = (
                f'NavigateToPose action server not available: '
                f'{self._nav_action_name}'
            )
            self.get_logger().error(message)
            return False, message

        nav_goal = NavigateToPose.Goal()
        nav_goal.pose = self._make_pose_stamped(pose)
        self.get_logger().info(
            f'Sending Nav2 goal to {self._nav_action_name} '
            f'for {step_name}.')

        nav_goal_handle = None
        for attempt in range(1, 6):
            send_future = self._nav_client.send_goal_async(
                nav_goal,
                feedback_callback=lambda feedback: self._on_nav_feedback(
                    feedback,
                    step_name,
                ),
            )
            if not self._wait_for_future(send_future, 5.0):
                message = f'Timed out sending navigation goal for {step_name}'
                self.get_logger().error(message)
                return False, message

            nav_goal_handle = send_future.result()
            if nav_goal_handle is not None and nav_goal_handle.accepted:
                break

            self.get_logger().warn(
                f'Navigation goal rejected for {step_name} '
                f'(attempt {attempt}/5). Retrying...')
            time.sleep(1.0)

        if nav_goal_handle is None or not nav_goal_handle.accepted:
            message = f'Navigation goal rejected for {step_name}'
            self.get_logger().error(message)
            return False, message

        self.get_logger().info(
            f'Navigating {step_name}: x={pose.x:.2f}, '
            f'y={pose.y:.2f}, yaw={pose.yaw:.2f}')

        result_future = nav_goal_handle.get_result_async()
        start_time = time.monotonic()
        while not result_future.done():
            if goal_handle is not None and goal_handle.is_cancel_requested:
                nav_goal_handle.cancel_goal_async()
                return False, 'Canceled'

            elapsed = time.monotonic() - start_time
            if elapsed > self._goal_timeout:
                nav_goal_handle.cancel_goal_async()
                message = f'Navigation timed out during {step_name}'
                self.get_logger().error(message)
                return False, message

            progress = self._interpolate_progress(
                start_progress,
                end_progress,
                elapsed / max(self._goal_timeout, 1.0),
            )
            if goal_handle is not None:
                self._publish_feedback(goal_handle, step_name, progress)
            time.sleep(0.2)

        nav_result = result_future.result()
        if nav_result.status != GoalStatus.STATUS_SUCCEEDED:
            message = (
                f'Navigation failed during {step_name} '
                f'(status={nav_result.status})'
            )
            self.get_logger().error(message)
            return False, message

        if goal_handle is not None:
            self._publish_feedback(goal_handle, step_name, end_progress)
        return True, f'Navigation complete: {step_name}'

    def _on_nav_feedback(self, feedback_msg, step_name: str):
        fb = feedback_msg.feedback
        self.get_logger().debug(
            f'{step_name}: distance_remaining={fb.distance_remaining:.2f}')

    def _wait_for_future(self, future, timeout_sec: float) -> bool:
        deadline = time.monotonic() + timeout_sec
        while not future.done() and time.monotonic() < deadline:
            time.sleep(0.05)
        return future.done()

    def _publish_feedback(self, goal_handle, current_step: str, progress: float):
        feedback = ServeTask.Feedback()
        feedback.current_step = current_step
        feedback.progress = float(max(0.0, min(progress, 1.0)))
        goal_handle.publish_feedback(feedback)

    def _interpolate_progress(
        self,
        start: float,
        end: float,
        ratio: float,
    ) -> float:
        bounded_ratio = max(0.0, min(ratio, 1.0))
        return start + (end - start) * bounded_ratio

    def _make_pose_stamped(self, pose: MapPose) -> PoseStamped:
        msg = PoseStamped()
        msg.header.frame_id = 'map'
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.pose.position.x = pose.x
        msg.pose.position.y = pose.y
        msg.pose.position.z = 0.0
        msg.pose.orientation.z = math.sin(pose.yaw / 2.0)
        msg.pose.orientation.w = math.cos(pose.yaw / 2.0)
        return msg

    def _publish_home_initial_pose_once(self):
        if self._initial_pose_sent:
            return
        home = self._poses.get('home')
        if home is None:
            self._initial_pose_sent = True
            return

        msg = PoseWithCovarianceStamped()
        msg.header.frame_id = 'map'
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.pose.pose.position.x = home.x
        msg.pose.pose.position.y = home.y
        msg.pose.pose.orientation.z = math.sin(home.yaw / 2.0)
        msg.pose.pose.orientation.w = math.cos(home.yaw / 2.0)
        msg.pose.covariance[0] = 0.25
        msg.pose.covariance[7] = 0.25
        msg.pose.covariance[35] = 0.0685

        self._initial_pose_pub.publish(msg)
        self._initial_pose_sent = True
        self.get_logger().info('Published initial pose at home.')


def main(args=None):
    rclpy.init(args=args)
    node = MoveActionServer()
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        executor.remove_node(node)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
