/**
 * Toast Component Tests
 * Basic smoke tests for toast notification system
 */

import { describe, it, expect } from 'vitest';
import { toast } from '../components/Toast';

describe('Toast System', () => {
  it('should have success method', () => {
    expect(toast.success).toBeDefined();
    expect(typeof toast.success).toBe('function');
  });

  it('should have error method', () => {
    expect(toast.error).toBeDefined();
    expect(typeof toast.error).toBe('function');
  });

  it('should have info method', () => {
    expect(toast.info).toBeDefined();
    expect(typeof toast.info).toBe('function');
  });

  it('should have warning method', () => {
    expect(toast.warning).toBeDefined();
    expect(typeof toast.warning).toBe('function');
  });

  it('should not throw when calling toast methods', () => {
    expect(() => toast.success('Test message')).not.toThrow();
    expect(() => toast.error('Test error')).not.toThrow();
    expect(() => toast.info('Test info')).not.toThrow();
    expect(() => toast.warning('Test warning')).not.toThrow();
  });
});
