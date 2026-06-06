# LLM Serving Robot — Workspace

ROS 2 + Gazebo 기반 LLM 서빙 로봇 프로젝트 워크스페이스입니다.

## 패키지 구성

| 패키지 | 담당 | 설명 |
|--------|------|------|
| `llm_serving_msgs` | 공통 | 커스텀 메시지·액션 정의 |
| `llm_serving_core` | Group B | LLM 에이전트, 태스크 실행, 상태 관리 |
| `llm_serving_gazebo` | Group A | Gazebo 시뮬레이션, 로봇 모델, 안전 제어 |

## 월드 맵

시뮬레이션 월드는 패키지에 포함된 **RoboRestaurant** 맵을 사용합니다.

```
llm_serving_gazebo/worlds/RoboRestaurant__.world
```

## 빌드 & 실행

```bash
cd llm_serving_project_ws
colcon build --symlink-install
source install/setup.bash

# 시뮬레이션 (Group A)
ros2 launch llm_serving_gazebo sim_environment.launch.py

# 코어 시스템 (Group B)
ros2 launch llm_serving_core core_system.launch.py
```

## 아키텍처

```
[User Input] → /user_command (Topic)     /guest_command (손님 입·퇴장)
      ↓                                           ↓
[LLM Agent] ← /table_status              [Table State Node]
      ↓         (테이블별 손님 수 배열)
 JSON 파싱 → 태스크 시퀀스
      ↓
[Task Executor] → ServeTask Action → [Move Action Server]
      ↓                                    ↓
[Robot State Node] ← /robot_status    [Gazebo + Safety Controller]
```

## 테이블 손님 상태

`table_state_node`가 테이블별 손님 수를 배열로 관리하고 `/table_status`로 공유합니다.
`guest_counts[i]` = (i+1)번 테이블 인원, `0`이면 빈 테이블.

**터미널 입력 예시 (user_input_node):**
- `손님 2명 입장` — 빈 테이블에 자동 배정
- `2번 테이블에 손님 4명` — 지정 테이블 배정
- `1번 테이블 퇴장` — 테이블 비우기
- `테이블 상태` — 현재 상태 로그 출력

**서비스 (ros2 service call):**
```bash
ros2 service call /seat_guests llm_serving_msgs/srv/SeatGuests "{party_size: 3, table_number: 0}"
ros2 service call /leave_table llm_serving_msgs/srv/LeaveTable "{table_number: 1}"
```

## 프롬프트 설계

- 시스템 프롬프트: `llm_serving_core/prompts/system_prompt.txt`
- LLM 출력은 반드시 JSON 형식 (action, destination, items 등)

## 트러블슈팅 기록

| 날짜 | 증상 | 원인 | 해결 |
|------|------|------|------|
| | | | |
