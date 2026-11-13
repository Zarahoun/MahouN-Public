/**
 * API Client Tests
 * Basic smoke tests for mahounClient
 */

import { describe, it, expect } from 'vitest';
import * as mahounClient from '../api/mahounClient';

describe('MAHOUN API Client', () => {
  it('should export uploadDocument function', () => {
    expect(mahounClient.uploadDocument).toBeDefined();
    expect(typeof mahounClient.uploadDocument).toBe('function');
  });

  it('should export analyzeDelay function', () => {
    expect(mahounClient.analyzeDelay).toBeDefined();
    expect(typeof mahounClient.analyzeDelay).toBe('function');
  });

  it('should export generateClaim function', () => {
    expect(mahounClient.generateClaim).toBeDefined();
    expect(typeof mahounClient.generateClaim).toBe('function');
  });

  it('should export askContract function', () => {
    expect(mahounClient.askContract).toBeDefined();
    expect(typeof mahounClient.askContract).toBe('function');
  });

  it('should export report generation functions', () => {
    expect(mahounClient.generateDelayReport).toBeDefined();
    expect(mahounClient.generateTimelineReport).toBeDefined();
    expect(mahounClient.getReport).toBeDefined();
    expect(mahounClient.listReports).toBeDefined();
  });
});
