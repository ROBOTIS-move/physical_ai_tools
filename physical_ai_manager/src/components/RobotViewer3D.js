import React, { useRef, useEffect, useMemo, useState, useCallback, useImperativeHandle, forwardRef } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { OrbitControls, Grid } from '@react-three/drei';
import * as THREE from 'three';
import { MdCenterFocusStrong } from 'react-icons/md';
import useUrdfRobot from '../hooks/useUrdfRobot';
import useJointStateSubscription from '../hooks/useJointStateSubscription';

const CAMERA_PRESETS = {
  perspective: { label: '3/4' },
  front:       { label: 'Front' },
  side:        { label: 'Side' },
  top:         { label: 'Top' },
};

function RobotModel({ robot }) {
  const groupRef = useRef();

  useEffect(() => {
    const group = groupRef.current;
    if (!robot || !group) return;
    group.add(robot);
    return () => {
      if (robot.parent === group) {
        group.remove(robot);
      }
    };
  }, [robot]);

  return <group ref={groupRef} rotation={[-Math.PI / 2, 0, 0]} />;
}

const CameraController = forwardRef(function CameraController({ robot }, ref) {
  const { camera } = useThree();
  const controlsRef = useRef();
  const centerRef = useRef(new THREE.Vector3());
  const baseDist = useRef(1);
  const initialized = useRef(false);

  useEffect(() => {
    if (!robot || initialized.current) return;

    const box = new THREE.Box3().setFromObject(robot);
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    const maxDim = Math.max(size.x, size.y, size.z);

    centerRef.current.copy(center);
    baseDist.current = maxDim;
    initialized.current = true;

    applyPreset('perspective', false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [robot]);

  const applyPreset = useCallback((presetName) => {
    if (!CAMERA_PRESETS[presetName]) return;

    const c = centerRef.current;
    const d = baseDist.current * 1.8;
    let pos;

    switch (presetName) {
      case 'front':
        pos = [c.x + d, c.y + d * 0.15, c.z];
        break;
      case 'side':
        pos = [c.x, c.y + d * 0.15, c.z + d];
        break;
      case 'top':
        pos = [c.x + 0.01, c.y + d * 1.2, c.z];
        break;
      case 'perspective':
      default:
        pos = [c.x + d * 0.7, c.y + d * 0.5, c.z + d * 0.7];
        break;
    }

    camera.position.set(...pos);
    camera.lookAt(c);
    camera.updateProjectionMatrix();
    if (controlsRef.current) {
      controlsRef.current.target.copy(c);
      controlsRef.current.update();
    }
  }, [camera]);

  useImperativeHandle(ref, () => ({
    applyPreset,
  }), [applyPreset]);

  return (
    <OrbitControls
      ref={controlsRef}
      makeDefault
      enableDamping
      dampingFactor={0.1}
      minDistance={0.3}
      maxDistance={10}
    />
  );
});

function SharedScene({ showGrid }) {
  return (
    <>
      <ambientLight intensity={0.6} />
      <directionalLight position={[5, 10, 5]} intensity={0.8} castShadow />
      <directionalLight position={[-3, 5, -3]} intensity={0.3} />
      {showGrid && (
        <Grid
          args={[10, 10]}
          cellSize={0.1}
          cellThickness={0.5}
          cellColor="#6b7280"
          sectionSize={0.5}
          sectionThickness={1}
          sectionColor="#374151"
          fadeDistance={5}
          fadeStrength={1}
          followCamera={false}
          infiniteGrid
        />
      )}
    </>
  );
}

function SceneContent({ robot, showGrid, cameraRef }) {
  return (
    <>
      <SharedScene showGrid={showGrid} />
      {robot && <RobotModel robot={robot} />}
      <CameraController ref={cameraRef} robot={robot} />
    </>
  );
}

function ReplaySceneContent({ robot, jointData, currentTime, showGrid, cameraRef }) {
  const lastAppliedTime = useRef(-1);

  useFrame(() => {
    if (!robot || currentTime === lastAppliedTime.current) return;
    lastAppliedTime.current = currentTime;

    const source = jointData;
    if (!source?.timestamps?.length || !source?.names?.length || !source?.positions?.length) return;

    let idx = 0;
    for (let i = 0; i < source.timestamps.length; i++) {
      if (source.timestamps[i] <= currentTime) idx = i;
      else break;
    }

    const numJoints = source.names.length;
    const startIdx = idx * numJoints;
    source.names.forEach((name, j) => {
      if (robot.joints[name]) {
        robot.joints[name].setJointValue(source.positions[startIdx + j] || 0);
      }
    });
  });

  return (
    <>
      <SharedScene showGrid={showGrid} />
      {robot && <RobotModel robot={robot} />}
      <CameraController ref={cameraRef} robot={robot} />
    </>
  );
}

function LoadingOverlay() {
  return (
    <div className="absolute inset-0 flex items-center justify-center bg-gray-900/80 z-10">
      <div className="flex flex-col items-center gap-2">
        <div className="w-8 h-8 border-2 border-blue-400 border-t-transparent rounded-full animate-spin" />
        <span className="text-white text-xs">Loading 3D Model...</span>
      </div>
    </div>
  );
}

function ErrorOverlay({ message, onRetry }) {
  return (
    <div className="absolute inset-0 flex items-center justify-center bg-gray-900/80 z-10">
      <div className="flex flex-col items-center gap-2 text-center px-4">
        <span className="text-red-400 text-xs">{message}</span>
        {onRetry && (
          <button
            onClick={onRetry}
            className="text-xs text-blue-400 hover:text-blue-300 underline"
          >
            Retry
          </button>
        )}
      </div>
    </div>
  );
}

function CameraPresetButtons({ onPreset, activePreset }) {
  return (
    <div className="absolute top-2 left-2 z-10 flex gap-1">
      {Object.entries(CAMERA_PRESETS).map(([key, preset]) => (
        <button
          key={key}
          onClick={() => onPreset(key)}
          className={`px-2 py-1 text-[10px] rounded font-medium transition-colors ${
            activePreset === key
              ? 'bg-blue-500 text-white'
              : 'bg-black/50 text-white/80 hover:bg-black/70'
          }`}
        >
          {preset.label}
        </button>
      ))}
    </div>
  );
}

export default function RobotViewer3D({
  mode = 'live',
  jointData = null,
  actionData = null,
  currentTime = 0,
  showGrid = true,
  className = '',
}) {
  const { robot, loading, error, setJointValues, reload } = useUrdfRobot();
  const cameraRef = useRef();
  const [activePreset, setActivePreset] = useState('perspective');

  useJointStateSubscription(setJointValues, mode === 'live' && !!robot);

  const handlePreset = useCallback((presetName) => {
    setActivePreset(presetName);
    cameraRef.current?.applyPreset(presetName);
  }, []);

  const canvasStyle = useMemo(() => ({
    background: 'linear-gradient(180deg, #1e293b 0%, #0f172a 100%)',
  }), []);

  return (
    <div className={`relative w-full h-full ${className}`}>
      {loading && <LoadingOverlay />}
      {error && <ErrorOverlay message={error} onRetry={reload} />}
      <CameraPresetButtons onPreset={handlePreset} activePreset={activePreset} />
      <Canvas
        camera={{ position: [1.5, 1.5, 1.5], fov: 50, near: 0.01, far: 100 }}
        style={canvasStyle}
        gl={{ antialias: true, alpha: false }}
        shadows
      >
        {mode === 'replay' ? (
          <ReplaySceneContent
            robot={robot}
            jointData={jointData}
            currentTime={currentTime}
            showGrid={showGrid}
            cameraRef={cameraRef}
          />
        ) : (
          <SceneContent robot={robot} showGrid={showGrid} cameraRef={cameraRef} />
        )}
      </Canvas>
      <button
        onClick={() => handlePreset(activePreset)}
        className="absolute bottom-2 right-2 z-10 p-1.5 bg-black/50 text-white/80 rounded hover:bg-black/70 transition-colors"
        title="Reset camera"
      >
        <MdCenterFocusStrong size={16} />
      </button>
    </div>
  );
}
