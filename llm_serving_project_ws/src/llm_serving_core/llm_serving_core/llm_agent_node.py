#!/usr/bin/env python3
"""LLM API 호출, JSON 파싱, 포맷/환각 필터링."""

from __future__ import annotations

import json
import os

import rclpy
import yaml
from ament_index_python.packages import get_package_share_directory
from llm_serving_core.env_loader import load_project_env
from llm_serving_core.order_command_parser import parse_order_command
from llm_serving_msgs.msg import TableStatus
from rclpy.node import Node
from std_msgs.msg import String


class LlmAgentNode(Node):
    def __init__(self):
        super().__init__('llm_agent_node')
        self.declare_parameter('model', 'gpt-4o-mini')
        self.declare_parameter('use_stub_fallback', True)

        env_file = load_project_env()
        self._model = self.get_parameter('model').value
        self._use_stub_fallback = self.get_parameter('use_stub_fallback').value
        self._api_key = os.environ.get('OPENAI_API_KEY', '').strip()
        self._openai_client = None

        if self._api_key:
            try:
                from openai import OpenAI
                self._openai_client = OpenAI(api_key=self._api_key)
                source = f'.env ({env_file})' if env_file else 'environment'
                self.get_logger().info(
                    f'OpenAI API enabled (model={self._model}, source={source}).')
            except ImportError:
                self.get_logger().error(
                    'openai 패키지가 없습니다: pip install openai')
                self._api_key = ''
        else:
            hint = (
                f'llm_serving_project_ws/.env 에 OPENAI_API_KEY를 설정하세요.'
                if env_file is None
                else f'{env_file} 에 OPENAI_API_KEY가 비어 있습니다.'
            )
            self.get_logger().warn(
                f'OpenAI API 키 없음 — 스텁 모드로 동작합니다. {hint}')

        share_dir = get_package_share_directory('llm_serving_core')
        prompt_path = os.path.join(share_dir, 'prompts', 'system_prompt.txt')
        with open(prompt_path, 'r', encoding='utf-8') as f:
            self.system_prompt = f.read()

        map_path = os.path.join(share_dir, 'config', 'restaurant_map.yaml')
        with open(map_path, 'r', encoding='utf-8') as f:
            restaurant_map = yaml.safe_load(f)
        self._table_names = [
            t['name'] for t in restaurant_map.get('tables', [])]

        menu_path = os.path.join(share_dir, 'config', 'menu_list.yaml')
        with open(menu_path, 'r', encoding='utf-8') as f:
            menu_data = yaml.safe_load(f)
        self._valid_items = self._load_menu_items(menu_data)

        self._guest_counts: list[int] = []
        self.create_subscription(
            TableStatus, 'table_status', self._on_table_status, 10)

        self.command_sub = self.create_subscription(
            String, 'user_command', self._on_command, 10)
        self.task_pub = self.create_publisher(String, 'llm_task', 10)
        self.get_logger().info('LLM agent node ready.')

    def _load_menu_items(self, menu_data: dict) -> set[str]:
        items: set[str] = set()
        for category in menu_data.get('menu', {}).values():
            if isinstance(category, list):
                items.update(category)
        return items

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
        parsed = self._parse_response(self._call_llm(user_text, table_context))
        if parsed is None:
            self.get_logger().warn('Failed to parse LLM response.')
            return

        if parsed.get('action') == 'unknown':
            reason = parsed.get('reason', '')
            self.get_logger().warn(f'Unknown action: {reason}')
            print(f'Robot: Sorry, {reason}')
            return

        validated = self._validate_order(parsed)
        if validated.get('action') == 'unknown':
            reason = validated.get('reason', '')
            self.get_logger().warn(f'Order rejected: {reason}')
            print(f'Robot: Sorry, {reason}')
            return

        out = String()
        out.data = json.dumps(validated, ensure_ascii=False)
        self.task_pub.publish(out)
        self.get_logger().info(f'Published task: {out.data}')

    def _validate_order(self, parsed: dict) -> dict:
        if parsed.get('action') != 'order':
            return {
                'action': 'unknown',
                'reason': 'only food orders are supported',
            }

        table = int(parsed.get('table', 0))
        items = parsed.get('items', [])

        if table <= 0 or table > len(self._table_names):
            return {
                'action': 'unknown',
                'reason': f'invalid table number: {table}',
            }

        guest_count = (
            self._guest_counts[table - 1]
            if table - 1 < len(self._guest_counts)
            else 0
        )
        if guest_count == 0:
            return {
                'action': 'unknown',
                'reason': f'table {table} has no guests',
            }

        invalid_items = [item for item in items if item not in self._valid_items]
        if invalid_items:
            return {
                'action': 'unknown',
                'reason': f'unknown menu items: {", ".join(invalid_items)}',
            }

        if not items:
            return {
                'action': 'unknown',
                'reason': 'no menu items in the order',
            }

        return {
            'action': 'order',
            'table': table,
            'destination': 'kitchen',
            'items': items,
            'reason': '',
        }

    def _call_openai(self, user_text: str, table_context: str) -> str:
        system_content = (
            f'{self.system_prompt}\n\n## Current Tables\n{table_context}'
        )
        response = self._openai_client.chat.completions.create(
            model=self._model,
            messages=[
                {'role': 'system', 'content': system_content},
                {'role': 'user', 'content': user_text},
            ],
            temperature=0,
            response_format={'type': 'json_object'},
        )
        return response.choices[0].message.content or ''

    def _call_stub(self, user_text: str) -> str:
        self.get_logger().warn('Using stub LLM response (API not configured).')
        stub = parse_order_command(
            user_text, self._valid_items, self._guest_counts)
        if stub is not None:
            return stub

        return json.dumps({
            'action': 'unknown',
            'table': 0,
            'destination': 'kitchen',
            'items': [],
            'reason': 'could not understand the order',
        }, ensure_ascii=False)

    def _call_llm(self, user_text: str, table_context: str) -> str:
        if self._openai_client is not None:
            try:
                return self._call_openai(user_text, table_context)
            except Exception as exc:
                self.get_logger().error(f'OpenAI API failed: {exc}')
                if not self._use_stub_fallback:
                    raise

        return self._call_stub(user_text)

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
