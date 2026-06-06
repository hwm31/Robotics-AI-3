#!/usr/bin/env python3
"""LLM API 호출, JSON 파싱, 포맷/환각 필터링."""

import json
import os

import rclpy
from ament_index_python.packages import get_package_share_directory
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

        self.command_sub = self.create_subscription(
            String, 'user_command', self._on_command, 10)
        self.task_pub = self.create_publisher(String, 'llm_task', 10)
        self.get_logger().info('LLM agent node ready.')

    def _on_command(self, msg: String):
        user_text = msg.data
        self.get_logger().info(f'Received command: {user_text}')

        # TODO: 실제 LLM API 호출 (OpenAI 등) — 환경변수 OPENAI_API_KEY 사용
        parsed = self._parse_response(self._call_llm(user_text))
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

    def _call_llm(self, user_text: str) -> str:
        """Placeholder — 실제 API 연동 시 교체."""
        self.get_logger().warn('Using stub LLM response (API not configured).')
        return json.dumps({
            'action': 'serve',
            'destination': 'table_1',
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
