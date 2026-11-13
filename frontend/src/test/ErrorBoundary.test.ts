/**
 * ErrorBoundary Component Tests
 * Basic smoke tests for error boundary
 */

import { describe, it, expect } from 'vitest';
import { Component } from 'react';
import ErrorBoundary from '../components/ErrorBoundary';

describe('ErrorBoundary Component', () => {
  it('should be a class component', () => {
    expect(ErrorBoundary.prototype).toBeInstanceOf(Component);
  });

  it('should have getDerivedStateFromError method', () => {
    expect(ErrorBoundary.getDerivedStateFromError).toBeDefined();
    expect(typeof ErrorBoundary.getDerivedStateFromError).toBe('function');
  });

  it('should return error state when error occurs', () => {
    const error = new Error('Test error');
    const state = ErrorBoundary.getDerivedStateFromError(error);

    expect(state).toHaveProperty('hasError', true);
    expect(state).toHaveProperty('error', error);
  });
});
