#!/usr/bin/env python3

"""
LLM 기반 음성 주문 해석 노드 — 손님 음성 주문 인식, 테이블 상태 반영, JSON 주문 계획 발행.

기능:
- 테이블 번호 + 좌표 토픽을 받아 현재 주문 대상 테이블 저장
- 마이크로 손님 주문 음성 입력
- 음성 인식 결과를 LLM에 전달
- 테이블 번호, 메뉴, 개수를 JSON 주문 계획으로 변환
- /order_plan 토픽 발행
- 테이블 좌표를 /table_location으로 재발행
"""

import json
import os
import re
import threading

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from openai import OpenAI
import speech_recognition as sr


class LlmOrderAgentNode(Node):
    def __init__(self):
        super().__init__('llm_order_agent_node')

        self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        self.model_name = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

        self.allowed_tables = [f"table_{i}" for i in range(1, 13)]

        self.current_table = None

        # 테이블 번호 + 좌표 토픽을 받은 직후 최초 주문 1회만 테이블 생략 허용
        self.allow_table_omission_once = False

        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()

        self.seated_table_sub = self.create_subscription(
            String,
            '/받는 토픽 이름',
            self.seated_table_callback,
            10
        )

        self.order_plan_pub = self.create_publisher(
            String,
            '/order_plan',
            10
        )

        self.table_location_pub = self.create_publisher(
            String,
            '/table_location',
            10
        )

        self.get_logger().info("=== llm_order_agent_node 시작 ===")
        self.get_logger().info("입력: 토픽 + 마이크 음성")
        self.get_logger().info("출력: /order_plan")

        # 마이크 입력은 계속 막히는 작업이라 별도 스레드에서 실행
        self.voice_thread = threading.Thread(
            target=self.voice_loop,
            daemon=True
        )
        self.voice_thread.start()

    def seated_table_callback(self, msg):
        data = self.parse_seated_table_data(msg.data.strip())

        if data is None:
            self.get_logger().warn(f"/seated_table 파싱 실패: {msg.data}")
            return

        table = data.get("table")

        if table is None:
            self.get_logger().warn(f"/seated_table에 table 정보가 없습니다: {data}")
            return

        if table not in self.allowed_tables:
            self.get_logger().warn(f"허용되지 않은 테이블: {table}")
            return

        self.current_table = table
        self.allow_table_omission_once = True

        self.get_logger().info(
            f"최초 주문 대상 테이블 설정: {self.current_table}, "
            f"테이블 생략 주문 1회 허용"
        )

        # 좌표 정보가 같이 들어왔으면 serving_task_node로 재발행
        if "x" in data and "y" in data:
            self.publish_table_location(data)
        else:
            self.get_logger().warn(
                f"{table} 좌표 정보가 없습니다."
            )

    def publish_table_location(self, data):
        table = data.get("table")
        x = data.get("x")
        y = data.get("y")

        if table is None or x is None or y is None:
            self.get_logger().warn(f"테이블 좌표 정보 부족: {data}")
            return

        if table not in self.allowed_tables:
            self.get_logger().warn(f"허용되지 않은 테이블: {table}")
            return

        try:
            x = float(x)
            y = float(y)
        except ValueError:
            self.get_logger().warn(f"좌표값이 숫자가 아닙니다: x={x}, y={y}")
            return

        msg = String()
        msg.data = json.dumps(
            {
                "table": table,
                "x": x,
                "y": y
            },
            ensure_ascii=False
        )

        self.table_location_pub.publish(msg)

        self.get_logger().info(f"/table_location 발행: {msg.data}")

    #받는 토픽 내용에 따라 변경할 것
    def parse_seated_table_data(self, raw):
        # case 1: {"table": "table_3", "people": 4, "x": 2.0, "y": -0.5}
        try:
            data = json.loads(raw)

            if isinstance(data, dict) and "table" in data:
                return data

        except json.JSONDecodeError:
            pass

        # case 2: "table_3"
        if re.fullmatch(r"table_([1-9]|1[0-2])", raw):
            return {
                "table": raw
            }

        # case 3: "3"
        if raw.isdigit():
            return {
                "table": f"table_{raw}"
            }

        # case 4: "3번"
        match = re.search(r"(\d+)\s*번", raw)
        if match:
            return {
                "table": f"table_{match.group(1)}"
            }

        return None

    def voice_loop(self):
        while rclpy.ok():
            user_order_text = self.listen_order()

            if user_order_text is None:
                continue

            self.get_logger().info(f"음성 주문 인식: {user_order_text}")

            order_plan = self.ask_llm(user_order_text)

            if order_plan.get("valid") is True:
                used_current_table = order_plan.get("used_current_table", False)

                if used_current_table:
                    self.allow_table_omission_once = False
                    self.get_logger().info("테이블 생략 주문 1회 사용 완료")

            out = String()
            out.data = json.dumps(order_plan, ensure_ascii=False)

            self.order_plan_pub.publish(out)
            self.get_logger().info(f"/order_plan 발행: {out.data}")

    def listen_order(self):
        try:
            with self.microphone as source:
                self.get_logger().info("🎤 주문을 말씀해주세요.")
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = self.recognizer.listen(source)

            text = self.recognizer.recognize_google(audio, language="ko-KR")
            return text

        except sr.UnknownValueError:
            self.get_logger().warn("음성을 인식하지 못했습니다.")
            return None

        except sr.RequestError as e:
            self.get_logger().error(f"음성 인식 서비스 오류: {e}")
            return None

        except Exception as e:
            self.get_logger().error(f"마이크 처리 오류: {e}")
            return None

    def ask_llm(self, user_order_text):
        system_prompt = """
You are an order parser for a ROS2 serving robot.

Convert the user's Korean food order into JSON only.

Allowed tables:
table_1, table_2, table_3, table_4, table_5, table_6,
table_7, table_8, table_9, table_10, table_11, table_12

Allowed menu items:
- water: 물, 워터
- coffee: 커피
- steak: 스테이크
- pasta: 파스타

Output JSON format:
{
  "valid": true,
  "message": "short Korean message",
  "used_current_table": false,
  "orders": [
    {
      "table": "table_1",
      "item": "water",
      "count": 1
    }
  ]
}

Critical rules:
1. Return JSON only. Do not use markdown.
2. If the user explicitly mentions a table number, use that table.
3. If the user says "여기", "이 테이블", "저희 테이블", "우리 테이블", or similar location-relative expressions, do not guess the table.
   Return:
   {
     "valid": false,
     "message": "테이블 번호를 말씀해주세요.",
     "used_current_table": false,
     "orders": []
   }
4. If the user does not mention a table number:
   - Use current_table only when allow_table_omission_once is true.
   - In that case, set used_current_table to true.
5. If the user does not mention a table number and allow_table_omission_once is false:
   Return valid false and ask for the table number.
6. If one table has multiple menu items, create multiple orders.
7. If multiple tables are explicitly mentioned, create orders in the spoken order.
8. If count is not mentioned, use count 1.
9. If menu item is missing or not allowed, return valid false.
10. If table number is outside 1 to 12, return valid false.
11. Use only allowed English item names: water, coffee, steak, pasta.

Examples:

Input:
{
  "current_table": "table_3",
  "allow_table_omission_once": true,
  "user_order_text": "파스타 2개랑 커피 1개 주세요"
}
Output:
{
  "valid": true,
  "message": "3번 테이블 주문을 생성했습니다.",
  "used_current_table": true,
  "orders": [
    {"table": "table_3", "item": "pasta", "count": 2},
    {"table": "table_3", "item": "coffee", "count": 1}
  ]
}

Input:
{
  "current_table": "table_3",
  "allow_table_omission_once": true,
  "user_order_text": "여기 물 주세요"
}
Output:
{
  "valid": false,
  "message": "테이블 번호를 말씀해주세요.",
  "used_current_table": false,
  "orders": []
}

Input:
{
  "current_table": "table_3",
  "allow_table_omission_once": false,
  "user_order_text": "물 하나 추가해주세요"
}
Output:
{
  "valid": false,
  "message": "테이블 번호를 말씀해주세요.",
  "used_current_table": false,
  "orders": []
}

Input:
{
  "current_table": "table_3",
  "allow_table_omission_once": false,
  "user_order_text": "7번 테이블에 물 하나 추가해주세요"
}
Output:
{
  "valid": true,
  "message": "7번 테이블 주문을 생성했습니다.",
  "used_current_table": false,
  "orders": [
    {"table": "table_7", "item": "water", "count": 1}
  ]
}
"""

        llm_input = {
            "current_table": self.current_table,
            "allow_table_omission_once": self.allow_table_omission_once,
            "user_order_text": user_order_text
        }

        try:
            response = self.client.responses.create(
                model=self.model_name,
                input=[
                    {
                        "role": "system",
                        "content": system_prompt
                    },
                    {
                        "role": "user",
                        "content": json.dumps(llm_input, ensure_ascii=False)
                    }
                ]
            )

            text = response.output_text.strip()
            return json.loads(text)

        except Exception as e:
            self.get_logger().error(f"LLM 호출 또는 JSON 파싱 실패: {e}")

            return {
                "valid": False,
                "message": "LLM 응답 처리에 실패했습니다.",
                "used_current_table": False,
                "orders": []
            }


def main(args=None):
    rclpy.init(args=args)

    node = LlmOrderAgentNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()