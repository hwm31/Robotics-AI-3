#!/usr/bin/env python3
"""자연어 명령 입력 → /user_command, /guest_command 토픽 발행."""

from __future__ import annotations

import select
import sys
import termios
import threading
import tty

import rclpy
from llm_serving_core.guest_command_parser import parse_guest_command
from llm_serving_core.speech_input import SpeechInputError, SpeechInputHandler
from rclpy.node import Node
from std_msgs.msg import String


class UserInputNode(Node):
    def __init__(self):
        super().__init__('user_input_node')
        self.declare_parameter('input_mode', 'text')
        self.declare_parameter('speech_language', 'ko-KR')
        self.declare_parameter('voice_trigger_key', 'v')
        self.declare_parameter('ambient_noise_duration', 0.5)

        self.input_mode = self.get_parameter('input_mode').value
        self.voice_trigger_key = self.get_parameter('voice_trigger_key').value.lower()
        self._voice_enabled = self.input_mode in ('voice', 'both')
        self._text_enabled = self.input_mode in ('text', 'both')

        if self.input_mode not in ('text', 'voice', 'both'):
            raise ValueError('input_mode must be one of: text, voice, both')

        self.publisher_ = self.create_publisher(String, 'user_command', 10)
        self.guest_pub = self.create_publisher(String, 'guest_command', 10)

        self._speech_handler: SpeechInputHandler | None = None
        self._is_recording = False
        self._stdin_is_tty = sys.stdin.isatty()
        self._line_buffer: list[str] = []
        self._terminal_settings = None

        if self._voice_enabled:
            if not self._stdin_is_tty:
                self.get_logger().warn(
                    'stdin이 TTY가 아니어 음성 모드를 비활성화합니다.')
                self._voice_enabled = False
                if not self._text_enabled:
                    self.input_mode = 'text'
                    self._text_enabled = True
            else:
                try:
                    self._speech_handler = SpeechInputHandler(
                        language=self.get_parameter('speech_language').value,
                        ambient_noise_duration=self.get_parameter(
                            'ambient_noise_duration').value,
                    )
                except SpeechInputError as exc:
                    self.get_logger().error(str(exc))
                    raise

        self._setup_terminal()
        self._log_ready_message()
        self.timer = self.create_timer(0.1, self._poll_input)

    def _setup_terminal(self) -> None:
        if self._voice_enabled and self._stdin_is_tty:
            self._terminal_settings = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin.fileno())

    def _restore_terminal(self) -> None:
        if self._terminal_settings is not None:
            termios.tcsetattr(
                sys.stdin, termios.TCSADRAIN, self._terminal_settings)

    def _log_ready_message(self) -> None:
        guest_hint = '"손님 2명 입장", "1번 테이블 퇴장"'
        order_hint = '"2번 테이블, 버거랑 콜라 주세요"'

        if self.input_mode == 'text':
            self.get_logger().info(
                f'텍스트 입력 대기. Guest: {guest_hint}. Order: {order_hint}. '
                'Enter로 전송, Ctrl+C 종료.')
        elif self.input_mode == 'voice':
            key = self.voice_trigger_key.upper()
            self.get_logger().info(
                f'음성 입력 대기. [{key}] 키를 누른 뒤 말씀해 주세요. '
                f'Guest: {guest_hint}. Order: {order_hint}. Ctrl+C 종료.')
        else:
            key = self.voice_trigger_key.upper()
            self.get_logger().info(
                f'텍스트/음성 입력 대기. Enter로 텍스트 전송, [{key}]로 음성 녹음. '
                f'Guest: {guest_hint}. Order: {order_hint}. Ctrl+C 종료.')

    def _publish_command(self, line: str, source: str) -> None:
        guest_json = parse_guest_command(line)
        if guest_json is not None:
            msg = String()
            msg.data = guest_json
            self.guest_pub.publish(msg)
            self.get_logger().info(
                f'Published guest_command ({source}): {guest_json}')
            return

        msg = String()
        msg.data = line
        self.publisher_.publish(msg)
        self.get_logger().info(f'Published command ({source}): {line}')

    def _start_voice_capture(self) -> None:
        if self._speech_handler is None or self._is_recording:
            return

        self._is_recording = True
        key = self.voice_trigger_key.upper()
        self.get_logger().info(f'[{key}] 녹음 중... 말씀 후 잠시 멈추면 종료됩니다.')

        def _capture() -> None:
            try:
                text = self._speech_handler.listen_once()
            except SpeechInputError as exc:
                self.get_logger().error(str(exc))
                text = None
            finally:
                self._is_recording = False

            if not text:
                self.get_logger().warn('음성을 인식하지 못했습니다.')
                return

            self.get_logger().info(f'음성 인식: "{text}"')
            self._publish_command(text, 'voice')

        threading.Thread(target=_capture, daemon=True).start()

    def _poll_text_line(self) -> None:
        if not select.select([sys.stdin], [], [], 0)[0]:
            return

        line = sys.stdin.readline().strip()
        if line:
            self._publish_command(line, 'text')

    def _poll_interactive_input(self) -> None:
        if not select.select([sys.stdin], [], [], 0)[0]:
            return

        char = sys.stdin.read(1)
        if char == '\x03':
            raise KeyboardInterrupt

        if char in ('\n', '\r'):
            line = ''.join(self._line_buffer).strip()
            self._line_buffer.clear()
            sys.stdout.write('\n')
            sys.stdout.flush()
            if line and self._text_enabled:
                self._publish_command(line, 'text')
            return

        if char in ('\x7f', '\b'):
            if self._line_buffer:
                self._line_buffer.pop()
                sys.stdout.write('\b \b')
                sys.stdout.flush()
            return

        if (
            self._voice_enabled
            and char.lower() == self.voice_trigger_key
            and not self._line_buffer
        ):
            self._start_voice_capture()
            return

        if self._text_enabled and (char.isprintable() or char == ' '):
            self._line_buffer.append(char)
            sys.stdout.write(char)
            sys.stdout.flush()

    def _poll_input(self) -> None:
        try:
            if self._voice_enabled:
                self._poll_interactive_input()
            else:
                self._poll_text_line()
        except KeyboardInterrupt:
            raise
        except Exception:
            pass

    def destroy_node(self) -> bool:
        self._restore_terminal()
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = UserInputNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
