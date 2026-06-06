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
[User Input] → /user_command (Topic)
      ↓
[LLM Agent] → JSON 파싱 → 태스크 시퀀스
      ↓
[Task Executor] → ServeTask Action → [Move Action Server]
      ↓                                    ↓
[Robot State Node] ← /robot_status    [Gazebo + Safety Controller]
```

## 프롬프트 설계

- 시스템 프롬프트: `llm_serving_core/prompts/system_prompt.txt`
- LLM 출력은 반드시 JSON 형식 (action, destination, items 등)

## 트러블슈팅 기록

| 날짜 | 증상 | 원인 | 해결 |
|------|------|------|------|
| | | | |
