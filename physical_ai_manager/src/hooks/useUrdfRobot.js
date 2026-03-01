import { useState, useEffect, useRef, useCallback } from 'react';
import * as THREE from 'three';
import URDFLoader from 'urdf-loader';
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader';

const DEFAULT_URDF_PATH = '/urdf/urdf/ffw_sg2_follower.urdf';

export default function useUrdfRobot(urdfPath = DEFAULT_URDF_PATH) {
  const [robot, setRobot] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const robotRef = useRef(null);

  const loadRobot = useCallback(() => {
    setLoading(true);
    setError(null);

    const loader = new URDFLoader();
    const stlLoader = new STLLoader();

    loader.packages = {
      'ffw_description': '/urdf/ffw_description',
    };

    loader.loadMeshCb = (path, _manager, onComplete) => {
      if (path.startsWith('file://') || path.startsWith('package://')) {
        const fallback = new THREE.Mesh(
          new THREE.BoxGeometry(0.02, 0.02, 0.02),
          new THREE.MeshStandardMaterial({ color: 0x888888, transparent: true, opacity: 0.3 })
        );
        onComplete(fallback);
        return;
      }

      stlLoader.load(
        path,
        (geometry) => {
          geometry.computeVertexNormals();
          const material = new THREE.MeshStandardMaterial({
            color: 0xcccccc,
            metalness: 0.3,
            roughness: 0.6,
          });
          const mesh = new THREE.Mesh(geometry, material);
          onComplete(mesh);
        },
        undefined,
        (_err) => {
          console.warn('Failed to load mesh:', path);
          const fallback = new THREE.Mesh(
            new THREE.BoxGeometry(0.02, 0.02, 0.02),
            new THREE.MeshStandardMaterial({ color: 0xff4444, transparent: true, opacity: 0.5 })
          );
          onComplete(fallback);
        }
      );
    };

    loader.load(
      urdfPath,
      (loadedRobot) => {
        loadedRobot.traverse((child) => {
          if (child.isMesh && child.material) {
            const urdfMaterial = child.userData?.urdfMaterial;
            if (urdfMaterial?.color) {
              child.material.color.setRGB(
                urdfMaterial.color.r,
                urdfMaterial.color.g,
                urdfMaterial.color.b
              );
              if (urdfMaterial.color.a !== undefined && urdfMaterial.color.a < 1) {
                child.material.transparent = true;
                child.material.opacity = urdfMaterial.color.a;
              }
            }
            child.castShadow = true;
            child.receiveShadow = true;
          }
        });

        robotRef.current = loadedRobot;
        setRobot(loadedRobot);
        setLoading(false);
      },
      undefined,
      (err) => {
        console.error('URDF load error:', err);
        setError(err?.message || 'Failed to load URDF');
        setLoading(false);
      }
    );
  }, [urdfPath]);

  useEffect(() => {
    loadRobot();
    return () => {
      if (robotRef.current) {
        robotRef.current.traverse((child) => {
          if (child.isMesh) {
            child.geometry?.dispose();
            if (child.material) {
              if (Array.isArray(child.material)) {
                child.material.forEach((m) => m.dispose());
              } else {
                child.material.dispose();
              }
            }
          }
        });
        robotRef.current = null;
      }
    };
  }, [loadRobot]);

  const setJointValues = useCallback((jointData) => {
    const r = robotRef.current;
    if (!r) return;
    if (Array.isArray(jointData.name)) {
      jointData.name.forEach((name, i) => {
        if (r.joints[name]) {
          r.joints[name].setJointValue(jointData.position[i]);
        }
      });
    } else if (typeof jointData === 'object') {
      Object.entries(jointData).forEach(([name, value]) => {
        if (r.joints[name]) {
          r.joints[name].setJointValue(value);
        }
      });
    }
  }, []);

  return { robot, loading, error, setJointValues, reload: loadRobot };
}
