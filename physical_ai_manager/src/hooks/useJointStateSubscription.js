import { useEffect, useRef, useCallback } from 'react';
import { useSelector } from 'react-redux';
import ROSLIB from 'roslib';

const JOINT_STATE_TOPICS = [
  { name: '/robot/arm_left_follower/joint_states', type: 'sensor_msgs/msg/JointState' },
  { name: '/robot/arm_right_follower/joint_states', type: 'sensor_msgs/msg/JointState' },
  { name: '/robot/head_follower/joint_states', type: 'sensor_msgs/msg/JointState' },
  { name: '/robot/lift_follower/joint_states', type: 'sensor_msgs/msg/JointState' },
];

const TRAJECTORY_TOPICS = [
  {
    name: '/leader/joint_trajectory_command_broadcaster_left/joint_trajectory',
    type: 'trajectory_msgs/msg/JointTrajectory',
  },
  {
    name: '/leader/joint_trajectory_command_broadcaster_right/joint_trajectory',
    type: 'trajectory_msgs/msg/JointTrajectory',
  },
];

const THROTTLE_MS = 33; // ~30fps

export default function useJointStateSubscription(setJointValues, enabled = true) {
  const rosHost = useSelector((state) => state.ros.rosHost);
  const subscribersRef = useRef([]);
  const lastUpdateRef = useRef(0);

  const handleJointState = useCallback(
    (msg) => {
      const now = Date.now();
      if (now - lastUpdateRef.current < THROTTLE_MS) return;
      lastUpdateRef.current = now;

      if (msg.name && msg.position) {
        setJointValues({ name: msg.name, position: msg.position });
      }
    },
    [setJointValues]
  );

  const handleTrajectory = useCallback(
    (msg) => {
      const now = Date.now();
      if (now - lastUpdateRef.current < THROTTLE_MS) return;
      lastUpdateRef.current = now;

      if (msg.joint_names && msg.points && msg.points.length > 0) {
        setJointValues({
          name: msg.joint_names,
          position: msg.points[0].positions,
        });
      }
    },
    [setJointValues]
  );

  useEffect(() => {
    if (!enabled || !rosHost) return;

    const ros = new ROSLIB.Ros({ url: `ws://${rosHost}:9090` });
    const subs = [];

    ros.on('connection', () => {
      JOINT_STATE_TOPICS.forEach((topic) => {
        const sub = new ROSLIB.Topic({
          ros,
          name: topic.name,
          messageType: topic.type,
          throttle_rate: THROTTLE_MS,
        });
        sub.subscribe(handleJointState);
        subs.push(sub);
      });

      TRAJECTORY_TOPICS.forEach((topic) => {
        const sub = new ROSLIB.Topic({
          ros,
          name: topic.name,
          messageType: topic.type,
          throttle_rate: THROTTLE_MS,
        });
        sub.subscribe(handleTrajectory);
        subs.push(sub);
      });

      subscribersRef.current = subs;
    });

    ros.on('error', (err) => {
      console.error('Joint state ROS connection error:', err);
    });

    return () => {
      subs.forEach((sub) => {
        try {
          sub.unsubscribe();
        } catch (_e) { /* ignore */ }
      });
      subscribersRef.current = [];
      try {
        ros.close();
      } catch (_e) { /* ignore */ }
    };
  }, [enabled, rosHost, handleJointState, handleTrajectory]);
}
