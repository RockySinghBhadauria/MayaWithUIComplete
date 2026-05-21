import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
});

export const getDashboard = () => api.get('/dashboard').then(r => r.data);

export const getCompanies = (params = {}) =>
  api.get('/companies', { params }).then(r => r.data);

export const getCompany = (id) =>
  api.get(`/companies/${id}`).then(r => r.data);

export const getOfficers = (params = {}) =>
  api.get('/officers', { params }).then(r => r.data);

export const getParsingSummary = (params = {}) =>
  api.get('/parsing-summary', { params }).then(r => r.data);

export const getPipelineSteps = () =>
  api.get('/pipeline/steps').then(r => r.data);

export const runPipeline = (body = {}) =>
  api.post('/pipeline/run', body).then(r => r.data);

export const getPipelineStatus = () =>
  api.get('/pipeline/status').then(r => r.data);

export const getPipelineHistory = () =>
  api.get('/pipeline/history').then(r => r.data);

export const getLogs = (limit = 100) =>
  api.get('/logs', { params: { limit } }).then(r => r.data);

export const getRssFeed = () =>
  api.get('/rss-feed').then(r => r.data);

export const getModuleOutput = (module) =>
  api.get('/module-output/' + module).then(r => r.data);

export const getStats = () =>
  api.get('/stats').then(r => r.data);

export const deleteTodayData = () =>
  api.delete('/data/today').then(r => r.data);

export const deleteAllData = () =>
  api.delete('/data/all').then(r => r.data);

export const stopPipeline = () =>
  api.post('/pipeline/stop').then(r => r.data);

export default api;
