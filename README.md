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
