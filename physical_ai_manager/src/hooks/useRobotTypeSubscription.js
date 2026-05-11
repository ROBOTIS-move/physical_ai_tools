// Subscribe to /robot_type topic so the Web UI auto-syncs with backend.
// Backend publishes (latched, TRANSIENT_LOCAL) on startup (DEFAULT_ROBOT_TYPE)
// and whenever /set_robot_type is called. New subscribers receive the last
// value immediately, so the page load picks up the current robot_type without
// the user having to re-select it from the dropdown.

import { useEffect } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import ROSLIB from 'roslib';
import { selectRobotType } from '../features/tasks/taskSlice';

export default function useRobotTypeSubscription() {
  const dispatch = useDispatch();
  const rosHost = useSelector((state) => state.ros.rosHost);
  const currentRobotType = useSelector((state) => state.tasks.taskStatus.robotType);

  useEffect(() => {
    if (!rosHost) return;

    const ros = new ROSLIB.Ros({ url: `ws://${rosHost}:9090` });
    let sub = null;

    ros.on('connection', () => {
      sub = new ROSLIB.Topic({
        ros,
        name: '/robot_type',
        messageType: 'std_msgs/msg/String',
      });
      sub.subscribe((msg) => {
        const next = (msg && msg.data) || '';
        if (next && next !== currentRobotType) {
          dispatch(selectRobotType(next));
        }
      });
    });

    ros.on('error', (err) => {
      console.error('robot_type ROS connection error:', err);
    });

    return () => {
      try { sub && sub.unsubscribe(); } catch (_e) { /* ignore */ }
      try { ros.close(); } catch (_e) { /* ignore */ }
    };
  }, [rosHost, dispatch, currentRobotType]);
}
