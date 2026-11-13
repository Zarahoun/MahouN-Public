/**
 * Training API Client Tests — Updated for Real Fine-Tuning Endpoints
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  startTrainingJob,
  getTrainingJobStatus,
  listTrainingJobs,
  getAvailableModels,
  getTrainingPresets,
} from '../api/trainingClient';

// Mock fetch globally
const fetchMock = vi.fn();
global.fetch = fetchMock as any;

describe('Training API Client', () => {
  beforeEach(() => {
    fetchMock.mockClear();
  });

  describe('startTrainingJob', () => {
    it('should start a training job successfully', async () => {
      const mockResponse = {
        job_id: 'job_123',
        model_name: 'dorna-llama-3-8b',
        status: 'pending',
        progress: 0,
        created_at: new Date().toISOString(),
      };

      fetchMock.mockResolvedValueOnce({
        ok: true,
        status: 201,
        headers: { get: () => 'application/json' },
        json: () => Promise.resolve(mockResponse),
      });

      const config = {
        model_name: 'dorna-llama-3-8b',
        training_mode: 'lora' as const,
        epochs: 3,
        batch_size: 4,
        learning_rate: 0.00002,
      };

      const result = await startTrainingJob(config);

      expect(fetchMock).toHaveBeenCalled();
      expect(result.job.id).toBe('job_123');
      expect(result.job.status).toBe('pending');
    });
  });

  describe('getTrainingJobStatus', () => {
    it('should get job status successfully', async () => {
      const mockJob = {
        job_id: 'job_123',
        model_name: 'dorna-llama-3-8b',
        status: 'training',
        progress: 45,
        created_at: '2026-08-27T00:00:00Z',
      };

      fetchMock.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: { get: () => 'application/json' },
        json: () => Promise.resolve(mockJob),
      });

      const result = await getTrainingJobStatus('job_123');

      expect(fetchMock).toHaveBeenCalled();
      expect(result.id).toBe('job_123');
      expect(result.status).toBe('training');
      expect(result.progress).toBe(45);
    });
  });

  describe('listTrainingJobs', () => {
    it('should list training jobs with parameters', async () => {
      const mockJobs = [
        { job_id: 'job_1', model_name: 'model1', status: 'running', progress: 50 },
        { job_id: 'job_2', model_name: 'model2', status: 'completed', progress: 100 },
      ];

      fetchMock.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: { get: () => 'application/json' },
        json: () => Promise.resolve(mockJobs),
      });

      const result = await listTrainingJobs('running' as any);

      expect(fetchMock).toHaveBeenCalled();
      expect(result).toHaveLength(2);
      expect(result[0].id).toBe('job_1');
    });
  });

  describe('getAvailableModels', () => {
    it('should return available models from API', async () => {
      const mockModels = {
        models: [
          { id: 'dorna-llama-3-8b', name: 'Dorna LLaMA 3', provider: 'local' },
          { id: 'persian-legal-bert', name: 'Persian Legal BERT', provider: 'local' },
        ],
      };

      fetchMock.mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: { get: () => 'application/json' },
        json: () => Promise.resolve(mockModels),
      });

      const result = await getAvailableModels();

      expect(result.models).toHaveLength(2);
      expect(result.models[0].id).toBe('dorna-llama-3-8b');
    });

    it('should return default legal models when API is unavailable', async () => {
      fetchMock.mockRejectedValueOnce(new Error('Network error'));

      const result = await getAvailableModels();

      expect(result.models.length).toBeGreaterThan(0);
      expect(result.models.some((m) => m.id === 'dorna-llama-3-8b')).toBe(true);
    });
  });

  describe('getTrainingPresets', () => {
    it('should return training presets', async () => {
      const result = await getTrainingPresets();

      expect(Array.isArray(result)).toBe(true);
      expect(result.length).toBeGreaterThan(0);
      expect(result[0]).toHaveProperty('model_name');
    });
  });
});
