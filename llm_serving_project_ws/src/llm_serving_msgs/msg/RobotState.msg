# 로봇 상태 (위치, 배터리, 적재물) — /robot_status 토픽용
std_msgs/Header header
geometry_msgs/Pose pose
float32 battery_percent
string[] loaded_items
string status
