# LLM Serving Robot Workspace

이 디렉터리는 ROS 2 워크스페이스의 `src` 영역입니다. 발표 및 평가 기준 중심의 전체 설명은 상위 README를 기준으로 합니다.

```text
../../README.md
```

## 패키지 구성

| 패키지 | 역할 |
| --- | --- |
| `llm_serving_msgs` | 커스텀 Message, Service, Action 인터페이스 |
| `llm_serving_core` | 입력 처리, LLM Agent, 테이블 상태, task 실행, 로봇 상태 |
| `llm_serving_gazebo` | Gazebo 월드/로봇 모델, Nav2 실행, 이동 Action Server, 안전 제어 |

## 빠른 실행

```bash
cd ..
colcon build --symlink-install
source install/setup.bash
```

터미널 1:

```bash
ros2 launch llm_serving_gazebo sim_environment.launch.py
```

터미널 2:

```bash
ros2 launch llm_serving_core core_system.launch.py input_mode:=text
```

## 주요 파일

| 파일 | 설명 |
| --- | --- |
| `llm_serving_core/prompts/system_prompt.txt` | LLM JSON 출력 규칙과 주문 처리 프롬프트 |
| `llm_serving_core/config/restaurant_map.yaml` | 주방, home, 12개 테이블 좌표와 좌석 수 |
| `llm_serving_core/config/menu_list.yaml` | 주문 검증용 메뉴 목록 |
| `llm_serving_gazebo/worlds/RoboRestaurant__.world` | Gazebo 식당 월드 |
| `llm_serving_gazebo/config/nav2_params.yaml` | Nav2 localization, planner, controller, costmap 설정 |
