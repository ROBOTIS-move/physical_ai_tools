import { useRef } from 'react';
import ROSLIB from 'roslib';

export function useRosServiceCaller(rosbridgeUrl) {
  const rosRef = useRef();

  function callService(serviceName, serviceType, request) {
    const ros = new ROSLIB.Ros({ url: rosbridgeUrl });
    const service = new ROSLIB.Service({
      ros,
      name: serviceName,
      serviceType: serviceType,
    });
    const req = new ROSLIB.ServiceRequest(request);
    service.callService(req, (result) => {
      // Process the result if necessary
      ros.close();
    });
  }

  function setGuiPage(pageName, option) {
    console.log('setGuiPage', pageName, option);
    callService('/gui/set_page', 'gaemi_interfaces/srv/SetGUIPage', {
      page_name: pageName,
      option: option,
    });
  }

  return { callService, setGuiPage };
}
