# Robotics-AI-3 — LLM Serving Robot

ROS 2 + Gazebo 기반 LLM 서빙 로봇 프로젝트입니다.

## 디렉터리 구조

```
Robotics-AI-3/
├── .gitignore
├── README.md
└── llm_serving_project_ws/
    └── src/
        ├── README.md              # 아키텍처, 프롬프트, 트러블슈팅
        ├── llm_serving_msgs/      # 커스텀 메시지·액션
        ├── llm_serving_core/      # Group B — LLM·태스크 실행
        └── llm_serving_gazebo/    # Group A — 시뮬레이션·안전 제어
```

## 월드 맵

## 시스템 구조도 및 맵 이미지

본 프로젝트의 ROS 2 노드/토픽 구조와 Gazebo 식당 맵 이미지는 아래와 같습니다.

### ROS 2 Node Graph

![ROS2 Node Graph](docs/ros2_node_graph.png)

위 구조도는 사용자 입력, LLM Agent, 테이블 상태 관리, 태스크 실행, Gazebo 이동 제어 노드가 ROS 2 Topic, Service, Action을 통해 어떻게 연결되는지 보여줍니다.

사용자 입력은 `user_input_node`를 통해 명령 토픽으로 전달됩니다.  
음식 주문과 관련된 자연어 명령은 `llm_agent_node`가 처리하고, 손님 입장 및 퇴장과 같은 테이블 상태 명령은 `table_state_node`가 처리합니다.

`llm_agent_node`는 사용자 명령을 LLM을 통해 JSON 형태의 주문 정보로 구조화한 뒤 `/llm_task` 토픽으로 발행합니다.  
이후 `task_executor_node`가 해당 작업을 받아 서빙 액션으로 변환하고, `move_action_server`와 Nav2 이동 구조를 통해 로봇 이동 흐름으로 연결됩니다.

### Restaurant Map

![Restaurant Map](docs/restaurant_map.png)

위 맵은 Gazebo/Nav2에서 사용하는 식당 환경입니다.  
흰색 영역은 로봇이 이동 가능한 공간이고, 검정색 영역은 벽, 테이블, 카운터 등 로봇이 이동할 수 없는 장애물 영역입니다.

초기 `restaurant_map.yaml`에서는 일부 테이블 좌표가 로봇이 실제로 도착해야 하는 위치가 아니라, 테이블 또는 장애물이 존재하는 검정색 영역 기준으로 설정되어 있었습니다.  
이로 인해 Nav2 goal을 보냈을 때 목표 지점이 occupied area 위에 위치하게 되었고, 경로 생성을 실패하면서 `ABORTED` 상태가 반환되었습니다.

따라서 테이블 중심 좌표를 그대로 Nav2 goal로 사용하는 것이 아니라, 테이블 앞의 이동 가능한 흰색 영역에 별도의 접근 좌표를 설정해야 합니다.

[`llm_serving_gazebo/worlds/RoboRestaurant__.world`](llm_serving_project_ws/src/llm_serving_gazebo/worlds/RoboRestaurant__.world) 를 사용합니다.

## 빠른 시작

```bash
cd llm_serving_project_ws
colcon build --symlink-install
source install/setup.bash

# 터미널 1 — 시뮬레이션
ros2 launch llm_serving_gazebo sim_environment.launch.py

# 터미널 2 — 코어 시스템
ros2 launch llm_serving_core core_system.launch.py
```

## 환경 변수

LLM API 사용 시 `.env` 파일에 키를 설정하세요 (`.gitignore`에 포함됨).

```
OPENAI_API_KEY=sk-...
```

자세한 내용은 [`llm_serving_project_ws/src/README.md`](llm_serving_project_ws/src/README.md)를 참고하세요.
