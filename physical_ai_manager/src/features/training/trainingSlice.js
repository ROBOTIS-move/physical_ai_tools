/*
 * Copyright 2025 ROBOTIS CO., LTD.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 *
 * Author: Kiwoong Park
 */

import { createSlice } from '@reduxjs/toolkit';

const initialState = {
  userList: [],
  datasetList: [],
  selectedUser: undefined,
  selectedDataset: undefined,
  policyList: [],
  deviceList: [],
  modelWeightList: [],
  selectedModelWeight: undefined,
  trainingMode: 'new', // 'new' or 'resume'
  isTraining: false, // training 진행 상태

  trainingInfo: {
    datasetRepoId: undefined,
    policyType: undefined,
    policyDevice: undefined,
    outputFolderName: undefined,
    resume: false,
    seed: 0,
    numWorkers: 0,
    batchSize: 0,
    steps: 0,
    evalFreq: 0,
    logFreq: '',
    saveFreq: '',
  },
};

const trainingSlice = createSlice({
  name: 'training',
  initialState,
  reducers: {
    setTrainingInfo: (state, action) => {
      state.trainingInfo = action.payload;
    },
    setUserList: (state, action) => {
      state.userList = action.payload;
    },
    setDatasetList: (state, action) => {
      state.datasetList = action.payload;
    },
    setSelectedUser: (state, action) => {
      state.selectedUser = action.payload;
    },
    setSelectedDataset: (state, action) => {
      state.selectedDataset = action.payload;
    },
    setDatasetRepoId: (state, action) => {
      state.trainingInfo.datasetRepoId = action.payload;
    },
    setPolicyList: (state, action) => {
      state.policyList = action.payload;
    },
    setDeviceList: (state, action) => {
      state.deviceList = action.payload;
    },
    selectPolicyType: (state, action) => {
      state.trainingInfo.policyType = action.payload;
    },
    selectPolicyDevice: (state, action) => {
      state.trainingInfo.policyDevice = action.payload;
    },
    setOutputFolderName: (state, action) => {
      state.trainingInfo.outputFolderName = action.payload;
    },
    setModelWeightList: (state, action) => {
      state.modelWeightList = action.payload;
    },
    setSelectedModelWeight: (state, action) => {
      state.selectedModelWeight = action.payload;
    },
    setTrainingMode: (state, action) => {
      state.trainingMode = action.payload;
    },
    setIsTraining: (state, action) => {
      state.isTraining = action.payload;
    },
  },
});

export const {
  setTrainingInfo,
  setUserList,
  setDatasetList,
  setSelectedUser,
  setSelectedDataset,
  setDatasetRepoId,
  setPolicyList,
  setDeviceList,
  selectPolicyType,
  selectPolicyDevice,
  setOutputFolderName,
  setModelWeightList,
  setSelectedModelWeight,
  setTrainingMode,
  setIsTraining,
} = trainingSlice.actions;

export default trainingSlice.reducer;
