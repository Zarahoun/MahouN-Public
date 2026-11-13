/**
 * MSW server for frontend tests.
 * Starts before all tests and stops after, intercepting fetch calls.
 */

import { setupServer } from 'msw/node';
import { handlers } from './handlers';

export const server = setupServer(...handlers);
