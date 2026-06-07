#!/usr/bin/env python3
"""다중 로봇 서빙 관제탑 (Dynamic Fleet Manager - Multi-Threaded & Bulletproof)"""

import json
import threading
import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor
from rclpy.callback_groups import ReentrantCallbackGroup
from std_msgs.msg import String
from llm_serving_msgs.action import ServeTask
from llm_serving_msgs.srv import SeatGuests
from rclpy.action import ActionClient

class FleetManagerNode(Node):
    def __init__(self):
        super().__init__('fleet_manager_node')
        
        # [멀티스레딩] 동시에 여러 콜백을 실행할 수 있는 그룹 생성
        self.cb_group = ReentrantCallbackGroup()
        
        # [멀티스레딩] 여러 스레드가 동시에 로봇 상태를 건드리지 못하게 잠금(Lock) 장치 생성
        self.state_lock = threading.Lock()
        
        # 1. 로봇 상태 추적
        self.robot_states = {'robot1': 'IDLE', 'robot2': 'IDLE'}
        
        # 2. 모든 클라이언트와 구독자에 callback_group 지정 (병렬 처리 허용)
        self.robot1_client = ActionClient(self, ServeTask, '/robot1/serve_task', callback_group=self.cb_group)
        self.robot2_client = ActionClient(self, ServeTask, '/robot2/serve_task', callback_group=self.cb_group)
        self.seat_client = self.create_client(SeatGuests, '/seat_guests', callback_group=self.cb_group)
        
        # 3. LLM 명령 및 주방 신호 구독
        self.llm_sub = self.create_subscription(String, 'llm_task', self._on_llm_task, 10, callback_group=self.cb_group)
        self.kitchen_sub = self.create_subscription(String, 'food_ready', self._on_food_ready, 10, callback_group=self.cb_group)
        
        self.get_logger().info('Multi-Threaded Dynamic Fleet Manager Node is Ready! 🚀🛡️')

    def _get_idle_robot(self):
        """현재 쉬고 있는(IDLE) 로봇을 안전하게 찾아 반환합니다."""
        with self.state_lock:
            for r_id, state in self.robot_states.items():
                if state == 'IDLE':
                    return r_id
        return None

    def _set_robot_state(self, robot_id, state):
        """로봇의 상태를 스레드-안전하게 변경합니다."""
        with self.state_lock:
            self.robot_states[robot_id] = state

    def _on_llm_task(self, msg: String):
        """LLM이 파싱한 JSON 명령 처리 (스레드 1)"""
        try:
            task = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().error('[예외 처리] LLM 신호 포맷 오류: 유효한 JSON이 아닙니다.')
            return
        
        intent = task.get('intent')
        
        if intent == 'greeting':
            # 빈 테이블을 시스템에 요청합니다.
            party_size = task.get('people', 1)
            self._request_seat_assignment(party_size)
            
        elif intent == 'order':
            # 쉬고 있는 로봇을 찾아 주문을 받으러 (주방으로) 보냅니다.
            table_num = task.get('table', 5)
            items = task.get('items', [])
            idle_robot = self._get_idle_robot()
            
            if idle_robot:
                self.get_logger().info(f"[주문] Table {table_num}에서 {items} 주문. {idle_robot} 배차 -> 주방으로 이동.")
                self._send_goal(idle_robot, destination='kitchen', table_number=table_num, items=items)
            else:
                self.get_logger().warn("[경고] 모든 로봇이 작업 중(BUSY)이라 주문을 수행할 수 없습니다!")
                
        else:
            self.get_logger().warn(f"[예외 처리] 알 수 없는 의도(Unknown intent): {intent}")

    def _request_seat_assignment(self, party_size):
        """table_state_node에 빈자리 할당을 요청하는 서비스 콜"""
        if not self.seat_client.wait_for_service(timeout_sec=3.0):
            self.get_logger().error('/seat_guests 서비스가 응답하지 않습니다.')
            return
            
        req = SeatGuests.Request()
        req.party_size = int(party_size)
        req.table_number = 0  # 0이면 시스템이 알아서 빈 테이블 배정
        
        future = self.seat_client.call_async(req)
        future.add_done_callback(lambda f: self._seat_assigned_cb(f, party_size))

    def _seat_assigned_cb(self, future, party_size):
        """빈자리 배정 완료 후 안내 로봇 출발"""
        try:
            response = future.result()
            if response.success:
                target_table = response.assigned_table
                idle_robot = self._get_idle_robot()
                
                if idle_robot:
                    self.get_logger().info(f"[안내] {party_size}명 -> Table {target_table} 배정 성공. {idle_robot} 배차.")
                    self._send_goal(idle_robot, destination='table', table_number=target_table)
                else:
                    self.get_logger().warn(f"[경고] 자리(Table {target_table})는 배정되었으나, 안내할 빈 로봇이 없습니다!")
            else:
                self.get_logger().warn("[알림] 만석입니다! 빈 테이블이 없습니다.")
        except Exception as e:
            self.get_logger().error(f"[예외 처리] 좌석 배정 서비스 실패: {e}")

    def _on_food_ready(self, msg: String):
        """주방 신호 처리 (스레드 2 - 배달) - 예외 처리 및 방어 로직 적용"""
        
        # 1. JSON 포맷 오류 방어 로직
        try:
            data = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().error("[예외 처리] 주방 신호 포맷 오류: 유효한 JSON이 아닙니다. 로봇 대기 유지.")
            return  # 시스템을 다운시키지 않고 해당 명령만 무시 (에러 필터링)

        # 2. 필수 데이터 누락 방어 로직
        target_table = data.get('table')
        if target_table is None:
            self.get_logger().error("[예외 처리] 주방 신호 오류: 목적지(table) 정보가 누락되었습니다. 배차 취소.")
            return

        # 3. 정상 배차 로직
        idle_robot = self._get_idle_robot()
        
        if idle_robot:
            self.get_logger().info(f"[배달] 음식 준비 완료! {idle_robot}을(를) 배차하여 Table {target_table}(으)로 보냅니다.")
            self._send_goal(idle_robot, destination='table', table_number=target_table, items=['food'])
        else:
            self.get_logger().warn("[경고] 음식이 나왔지만 배달할 빈 로봇이 없습니다. (모두 BUSY)")

    def _send_goal(self, robot_id, destination, table_number=0, items=None):
        """선택된 로봇에게 액션 목표(Goal) 전송"""
        if items is None:
            items = []
            
        client = self.robot1_client if robot_id == 'robot1' else self.robot2_client
        
        if not client.wait_for_server(timeout_sec=3.0):
            self.get_logger().error(f'[예외 처리] {robot_id} 액션 서버가 열려있지 않습니다!')
            return
            
        goal = ServeTask.Goal()
        goal.destination = destination
        goal.table_number = int(table_number)
        goal.items = items
        
        # [멀티스레딩 락 적용] 로봇 상태를 작업 중(BUSY)으로 안전하게 변경!
        self._set_robot_state(robot_id, 'BUSY')
        
        send_future = client.send_goal_async(goal)
        send_future.add_done_callback(lambda future, r_id=robot_id: self._goal_response_cb(future, r_id))

    def _goal_response_cb(self, future, robot_id):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().error(f'{robot_id}가 목표를 거부했습니다.')
            self._set_robot_state(robot_id, 'IDLE') # 실패했으므로 다시 대기 상태로 복구
            return
        
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(lambda future, r_id=robot_id: self._result_cb(future, r_id))

    def _result_cb(self, future, robot_id):
        """로봇 임무 완료 시 호출"""
        result = future.result().result
        self.get_logger().info(f'[{robot_id} 임무 완료] {result.message}')
        # 임무를 성공적으로 마쳤으므로 다시 다른 일을 할 수 있게 IDLE 상태로 변경!
        self._set_robot_state(robot_id, 'IDLE')


def main(args=None):
    rclpy.init(args=args)
    node = FleetManagerNode()
    
    # [멀티스레딩] 노드를 단일 스레드가 아닌 4개의 스레드로 병렬 실행!
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()