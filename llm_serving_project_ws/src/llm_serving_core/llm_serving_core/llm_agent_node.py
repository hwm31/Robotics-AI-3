#!/usr/bin/env python3
"""LLM API 호출, JSON 파싱, 포맷/환각 필터링."""

import json
import os

import rclpy
import yaml
from ament_index_python.packages import get_package_share_directory
from llm_serving_msgs.msg import TableStatus
from rclpy.node import Node
from std_msgs.msg import String


class LlmAgentNode(Node):
    def __init__(self):
        super().__init__('llm_agent_node')
        self.declare_parameter('model', 'gpt-4o-mini')

        share_dir = get_package_share_directory('llm_serving_core')
        prompt_path = os.path.join(share_dir, 'prompts', 'system_prompt.txt')
        with open(prompt_path, 'r', encoding='utf-8') as f:
            self.system_prompt = f.read()

        map_path = os.path.join(share_dir, 'config', 'restaurant_map.yaml')
        with open(map_path, 'r', encoding='utf-8') as f:
            restaurant_map = yaml.safe_load(f)
        self._table_names = [
            t['name'] for t in restaurant_map.get('tables', [])]

        self._guest_counts: list[int] = []
        self.create_subscription(
            TableStatus, 'table_status', self._on_table_status, 10)

        self.command_sub = self.create_subscription(
            String, 'user_command', self._on_command, 10)
        self.task_pub = self.create_publisher(String, 'llm_task', 10)
        self.get_logger().info('LLM agent node ready.')

    def _on_table_status(self, msg: TableStatus):
        self._guest_counts = list(msg.guest_counts)

    def _format_table_context(self) -> str:
        if not self._table_names:
            return 'No table information available.'
        lines = []
        for i, name in enumerate(self._table_names):
            count = self._guest_counts[i] if i < len(self._guest_counts) else 0
            state = f'{count} guests' if count > 0 else 'empty'
            lines.append(f'- {name}: {state}')
        return '\n'.join(lines)

    def _on_command(self, msg: String):
        user_text = msg.data
        self.get_logger().info(f'Received command: {user_text}')

        table_context = self._format_table_context()
        # TODO: 실제 LLM API 호출 (OpenAI 등) — 환경변수 OPENAI_API_KEY 사용
        parsed = self._parse_response(self._call_llm(user_text, table_context))
        if parsed is None:
            self.get_logger().warn('Failed to parse LLM response.')
            return

        if parsed.get('action') == 'unknown':
            self.get_logger().warn(f"Unknown action: {parsed.get('reason', '')}")
            return

        out = String()
        out.data = json.dumps(parsed, ensure_ascii=False)
        self.task_pub.publish(out)
        self.get_logger().info(f'Published task: {out.data}')

    def _call_llm(self, user_text: str, table_context: str) -> str:
        """Placeholder — 실제 API 연동 시 table_context를 프롬프트에 포함."""
        self.get_logger().warn('Using stub LLM response (API not configured).')
        self.get_logger().debug(f'Table context:\n{table_context}')

        destination = 'table_1'
        for i, name in enumerate(self._table_names):
            count = self._guest_counts[i] if i < len(self._guest_counts) else 0
            if count > 0:
                destination = name
                break

        return json.dumps({
            'action': 'serve',
            'destination': destination,
            'items': ['coke'],
            'reason': '',
        })

    def _parse_response(self, raw: str) -> dict | None:
        try:
            text = raw.strip()
            if text.startswith('```'):
                text = text.split('\n', 1)[-1].rsplit('```', 1)[0]
            return json.loads(text)
        except json.JSONDecodeError as e:
            self.get_logger().error(f'JSON parse error: {e}')
            return None


def main(args=None):
    rclpy.init(args=args)
    node = LlmAgentNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
